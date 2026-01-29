"""Workload executor for running benchmarks on agent."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, List

from common.models.workload import WorkloadTool
from common.models.metrics import Metrics, IOPSStats, ThroughputStats, LatencyStats

logger = logging.getLogger(__name__)


class WorkloadExecutor:
    """Execute workloads on the agent."""
    
    def __init__(self, agent_id: str, work_dir: Path):
        self.agent_id = agent_id
        self.work_dir = work_dir
        
        self._is_running = False
        self._is_paused = False
        self._current_execution_id: Optional[str] = None
        self._current_workload: Optional[str] = None
        self._current_process: Optional[asyncio.subprocess.Process] = None
        self._metrics_callback: Optional[Callable] = None
        self._stop_requested = False
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def current_execution_id(self) -> Optional[str]:
        return self._current_execution_id
    
    @property
    def current_workload(self) -> Optional[str]:
        return self._current_workload
    
    def set_metrics_callback(self, callback: Callable) -> None:
        """Set callback for metrics reporting."""
        self._metrics_callback = callback
    
    async def prepare(self, execution_id: str, config: dict) -> None:
        """Prepare for workload execution."""
        logger.info(f"Preparing execution: {execution_id}")
        
        # Create work directory for this execution
        exec_dir = self.work_dir / execution_id
        exec_dir.mkdir(parents=True, exist_ok=True)
        
        # Save config
        config_path = exec_dir / "config.json"
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        
        # Pre-create test files if needed
        tool = config.get("tool", "fio")
        if tool == "fio":
            await self._prepare_fio(exec_dir, config)
    
    async def _prepare_fio(self, exec_dir: Path, config: dict) -> None:
        """Prepare FIO test files."""
        test_config = config.get("test", {})
        file_size = test_config.get("file_size", "1G")
        
        # Create test file directory
        test_files_dir = exec_dir / "test_files"
        test_files_dir.mkdir(exist_ok=True)
        
        logger.debug(f"Prepared FIO test directory: {test_files_dir}")
    
    async def start(self, execution_id: str, config: dict) -> None:
        """Start workload execution."""
        if self._is_running:
            logger.warning(f"Already running execution: {self._current_execution_id}")
            return
        
        self._is_running = True
        self._current_execution_id = execution_id
        self._stop_requested = False
        
        tool = config.get("tool", "fio")
        self._current_workload = tool
        
        logger.info(f"Starting execution: {execution_id} with tool: {tool}")
        
        try:
            exec_dir = self.work_dir / execution_id
            exec_dir.mkdir(parents=True, exist_ok=True)
            
            if tool == "fio":
                await self._run_fio(execution_id, exec_dir, config)
            elif tool == "dd":
                await self._run_dd(execution_id, exec_dir, config)
            elif tool == "iozone":
                await self._run_iozone(execution_id, exec_dir, config)
            else:
                logger.error(f"Unknown tool: {tool}")
            
            logger.info(f"Execution completed: {execution_id}")
            
        except asyncio.CancelledError:
            logger.info(f"Execution cancelled: {execution_id}")
        except Exception as e:
            logger.error(f"Execution failed: {execution_id}: {e}")
        finally:
            self._is_running = False
            self._current_execution_id = None
            self._current_workload = None
            self._current_process = None
    
    async def _run_fio(self, execution_id: str, exec_dir: Path, config: dict) -> None:
        """Run FIO benchmark."""
        io_config = config.get("io", {})
        test_config = config.get("test", {})
        
        # Build FIO command
        duration = test_config.get("duration", 60)
        ramp_time = test_config.get("ramp_time", 0)
        file_size = test_config.get("file_size", "1G")
        
        block_size = io_config.get("block_size", "4k")
        io_depth = io_config.get("io_depth", 32)
        num_jobs = io_config.get("num_jobs", 1)
        pattern = io_config.get("pattern", "random")
        read_percent = io_config.get("read_percent", 100)
        direct_io = io_config.get("direct_io", True)
        
        # Determine rw mode
        if read_percent == 100:
            rw = "randread" if pattern == "random" else "read"
        elif read_percent == 0:
            rw = "randwrite" if pattern == "random" else "write"
        else:
            rw = "randrw" if pattern == "random" else "rw"
        
        # Test file path
        test_file = exec_dir / "test_files" / f"fio_test_{self.agent_id}"
        test_file.parent.mkdir(exist_ok=True)
        
        # FIO job file
        job_file = exec_dir / "fio_job.fio"
        job_content = f"""[global]
name={execution_id}
ioengine=libaio
direct={1 if direct_io else 0}
bs={block_size}
iodepth={io_depth}
numjobs={num_jobs}
time_based
runtime={duration}
ramp_time={ramp_time}
group_reporting

[workload]
rw={rw}
{"rwmixread=" + str(read_percent) if "rw" in rw else ""}
size={file_size}
filename={test_file}
"""
        
        with open(job_file, "w") as f:
            f.write(job_content)
        
        # Output file for JSON results
        output_file = exec_dir / "fio_output.json"
        
        # Build command
        cmd = [
            "fio",
            str(job_file),
            "--output-format=json",
            f"--output={output_file}",
            "--status-interval=1",
        ]
        
        logger.info(f"Running FIO: {' '.join(cmd)}")
        
        # Start FIO process
        self._current_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        # Monitor process and collect metrics
        start_time = time.time()
        
        while self._current_process.returncode is None:
            if self._stop_requested:
                self._current_process.terminate()
                break
            
            while self._is_paused and not self._stop_requested:
                await asyncio.sleep(0.5)
            
            # Parse any available metrics from status
            # FIO with status-interval outputs to stderr
            try:
                await asyncio.wait_for(
                    self._current_process.wait(),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                # Still running, collect metrics
                elapsed = time.time() - start_time
                
                # Report basic progress
                if self._metrics_callback:
                    metrics = Metrics(
                        client_id=self.agent_id,
                        execution_id=execution_id,
                        iops=IOPSStats(read=0, write=0, total=0),
                        throughput=ThroughputStats(read_bps=0, write_bps=0, total_bps=0),
                        latency_us=LatencyStats(avg=0),
                    )
                    await self._metrics_callback(metrics)
        
        # Parse final results
        if output_file.exists():
            await self._parse_fio_results(execution_id, output_file)
    
    async def _parse_fio_results(self, execution_id: str, output_file: Path) -> None:
        """Parse FIO JSON output."""
        try:
            with open(output_file) as f:
                results = json.load(f)
            
            for job in results.get("jobs", []):
                read_stats = job.get("read", {})
                write_stats = job.get("write", {})
                
                metrics = Metrics(
                    client_id=self.agent_id,
                    execution_id=execution_id,
                    iops=IOPSStats(
                        read=int(read_stats.get("iops", 0)),
                        write=int(write_stats.get("iops", 0)),
                        total=int(read_stats.get("iops", 0) + write_stats.get("iops", 0)),
                    ),
                    throughput=ThroughputStats(
                        read_bps=int(read_stats.get("bw_bytes", 0)),
                        write_bps=int(write_stats.get("bw_bytes", 0)),
                        total_bps=int(read_stats.get("bw_bytes", 0) + write_stats.get("bw_bytes", 0)),
                    ),
                    latency_us=LatencyStats(
                        avg=read_stats.get("lat_ns", {}).get("mean", 0) / 1000,
                        min=read_stats.get("lat_ns", {}).get("min", 0) / 1000,
                        max=read_stats.get("lat_ns", {}).get("max", 0) / 1000,
                        p50=read_stats.get("clat_ns", {}).get("percentile", {}).get("50.000000", 0) / 1000,
                        p99=read_stats.get("clat_ns", {}).get("percentile", {}).get("99.000000", 0) / 1000,
                    ),
                )
                
                if self._metrics_callback:
                    await self._metrics_callback(metrics)
                
                logger.info(
                    f"FIO Results - IOPS: {metrics.iops.total}, "
                    f"BW: {metrics.throughput.total_mbps:.2f} MB/s, "
                    f"Lat: {metrics.latency_us.avg:.2f} us"
                )
                
        except Exception as e:
            logger.error(f"Failed to parse FIO results: {e}")
    
    async def _run_dd(self, execution_id: str, exec_dir: Path, config: dict) -> None:
        """Run dd benchmark."""
        io_config = config.get("io", {})
        test_config = config.get("test", {})
        
        block_size = io_config.get("block_size", "1M")
        count = test_config.get("count", 1024)
        
        test_file = exec_dir / "test_files" / f"dd_test_{self.agent_id}"
        test_file.parent.mkdir(exist_ok=True)
        
        cmd = [
            "dd",
            f"if=/dev/zero",
            f"of={test_file}",
            f"bs={block_size}",
            f"count={count}",
            "oflag=direct",
        ]
        
        logger.info(f"Running dd: {' '.join(cmd)}")
        
        self._current_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        _, stderr = await self._current_process.communicate()
        
        # Parse dd output
        logger.info(f"dd output: {stderr.decode()}")
    
    async def _run_iozone(self, execution_id: str, exec_dir: Path, config: dict) -> None:
        """Run IOzone benchmark."""
        io_config = config.get("io", {})
        test_config = config.get("test", {})
        
        file_size = test_config.get("file_size", "1G")
        record_size = io_config.get("block_size", "64k")
        
        test_file = exec_dir / "test_files" / f"iozone_test_{self.agent_id}"
        test_file.parent.mkdir(exist_ok=True)
        
        cmd = [
            "iozone",
            "-a",
            "-s", file_size,
            "-r", record_size,
            "-f", str(test_file),
            "-R",
        ]
        
        logger.info(f"Running iozone: {' '.join(cmd)}")
        
        self._current_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout, stderr = await self._current_process.communicate()
        logger.info(f"IOzone completed")
    
    async def stop(self, execution_id: str = None) -> None:
        """Stop the current execution."""
        if execution_id and execution_id != self._current_execution_id:
            logger.warning(f"Execution {execution_id} not running")
            return
        
        logger.info(f"Stopping execution: {self._current_execution_id}")
        self._stop_requested = True
        
        if self._current_process and self._current_process.returncode is None:
            try:
                self._current_process.terminate()
                await asyncio.wait_for(self._current_process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._current_process.kill()
    
    async def pause(self, execution_id: str) -> None:
        """Pause the current execution."""
        if execution_id != self._current_execution_id:
            return
        
        logger.info(f"Pausing execution: {execution_id}")
        self._is_paused = True
        
        # Send SIGSTOP to pause process
        if self._current_process and self._current_process.returncode is None:
            try:
                os.kill(self._current_process.pid, signal.SIGSTOP)
            except Exception as e:
                logger.error(f"Failed to pause process: {e}")
    
    async def resume(self, execution_id: str) -> None:
        """Resume a paused execution."""
        if execution_id != self._current_execution_id:
            return
        
        logger.info(f"Resuming execution: {execution_id}")
        self._is_paused = False
        
        # Send SIGCONT to resume process
        if self._current_process and self._current_process.returncode is None:
            try:
                os.kill(self._current_process.pid, signal.SIGCONT)
            except Exception as e:
                logger.error(f"Failed to resume process: {e}")
    
    async def cleanup(self) -> None:
        """Cleanup resources."""
        if self._current_process and self._current_process.returncode is None:
            self._current_process.terminate()
            try:
                await asyncio.wait_for(self._current_process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._current_process.kill()
