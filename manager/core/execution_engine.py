"""Execution engine for orchestrating test runs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional, Any, Dict, List

from common.models.execution import ExecutionStatus, ExecutionPhase, Execution
from common.messaging.redis_client import RedisClient
from common.messaging.events import (
    Event, EventType,
    create_execution_start_event,
    create_execution_stop_event,
)
from manager.storage.data_store import DataStore
from manager.core.workload_executor import WorkloadExecutor

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Engine for orchestrating test executions."""
    
    def __init__(self, data_store: DataStore, redis_client: RedisClient):
        self.data_store = data_store
        self.redis_client = redis_client
        self.workload_executor = WorkloadExecutor()
        self._active_executions: dict[str, dict] = {}
        self._stop_flags: dict[str, bool] = {}
        self._pause_flags: dict[str, bool] = {}
    
    async def run_execution(
        self,
        execution_id: str,
        workload_config: dict,
        cluster_config: dict,
        run_prechecks: bool = True,
    ) -> None:
        """Run a complete test execution."""
        logger.info(f"Starting execution: {execution_id}")
        
        self._active_executions[execution_id] = {
            "status": ExecutionStatus.PENDING.value,
            "phase": ExecutionPhase.INIT.value,
            "started_at": datetime.utcnow().isoformat(),
            "clients": [],
            "current_iops": 0,
            "current_throughput_mbps": 0,
            "current_latency_us": 0,
        }
        self._stop_flags[execution_id] = False
        self._pause_flags[execution_id] = False
        
        try:
            # Phase 1: Prechecks
            if run_prechecks:
                await self._run_prechecks_phase(execution_id, workload_config, cluster_config)
                
                if self._stop_flags.get(execution_id):
                    await self._handle_stopped(execution_id)
                    return
            
            # Phase 2: Prepare
            await self._run_prepare_phase(execution_id, workload_config, cluster_config)
            
            if self._stop_flags.get(execution_id):
                await self._handle_stopped(execution_id)
                return
            
            # Phase 3: Execute
            await self._run_execution_phase(execution_id, workload_config, cluster_config)
            
            # Phase 4: Cleanup and complete
            await self._run_cleanup_phase(execution_id, workload_config)
            
            await self.data_store.update_execution_status(
                execution_id,
                ExecutionStatus.COMPLETED.value,
            )
            
            logger.info(f"Execution completed: {execution_id}")
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Execution failed: {execution_id}: {error_message}", exc_info=True)
            await self.data_store.update_execution_status(
                execution_id,
                ExecutionStatus.FAILED.value,
                error_message=error_message,
            )
            self.data_store.write_log(execution_id, f"Execution failed: {error_message}")
        finally:
            self._cleanup_execution(execution_id)
    
    async def _run_prechecks_phase(
        self,
        execution_id: str,
        workload_config: dict,
        cluster_config: dict,
    ) -> None:
        """Run prechecks phase."""
        logger.info(f"Running prechecks for execution: {execution_id}")
        
        await self.data_store.update_execution_status(
            execution_id,
            ExecutionStatus.PRECHECKS.value,
        )
        self._update_state(execution_id, phase=ExecutionPhase.PRECHECK.value)
        
        from manager.prechecks.runner import PrecheckRunner
        from common.models.cluster import ClusterConfig
        
        # Get clients
        clients = await self.data_store.get_clients()
        
        # Create cluster config object
        cluster = ClusterConfig(**cluster_config)
        
        # Run prechecks
        runner = PrecheckRunner(
            cluster_config=cluster,
            clients=clients,
            check_cluster=workload_config.get("prechecks", {}).get("cluster_health", True),
            check_clients=workload_config.get("prechecks", {}).get("client_health", True),
            check_network=workload_config.get("prechecks", {}).get("network_baseline", False),
            custom_commands=workload_config.get("prechecks", {}).get("custom_commands", []),
        )
        
        report = await runner.run_all_prechecks(execution_id)
        
        # Save report
        self.data_store.save_precheck_report(execution_id, report.model_dump())
        
        if not report.can_proceed:
            raise Exception(f"Prechecks failed: {report.blocking_issues}")
        
        # Store excluded clients
        self._active_executions[execution_id]["excluded_clients"] = report.excluded_clients
        
        logger.info(f"Prechecks passed for execution: {execution_id}")
    
    async def _run_prepare_phase(
        self,
        execution_id: str,
        workload_config: dict,
        cluster_config: dict,
    ) -> None:
        """Prepare clients for execution."""
        logger.info(f"Preparing execution: {execution_id}")
        
        await self.data_store.update_execution_status(
            execution_id,
            ExecutionStatus.PREPARING.value,
        )
        self._update_state(execution_id, phase=ExecutionPhase.PREPARE.value)
        
        # Get clients to use
        clients = await self.data_store.get_clients()
        excluded = self._active_executions[execution_id].get("excluded_clients", [])
        
        # Filter clients based on selection mode
        client_selection = workload_config.get("clients", {})
        mode = client_selection.get("mode", "all")
        
        available_clients = [
            c for c in clients
            if c.get("id") not in excluded
        ]
        
        if mode == "all":
            selected_clients = available_clients
        elif mode == "count":
            count = client_selection.get("count", len(available_clients))
            selected_clients = available_clients[:count]
        elif mode == "specific":
            client_ids = set(client_selection.get("client_ids", []))
            selected_clients = [c for c in available_clients if c.get("id") in client_ids]
        else:
            selected_clients = available_clients
        
        if not selected_clients:
            raise Exception("No clients available for execution")
        
        self._active_executions[execution_id]["clients"] = selected_clients
        self._active_executions[execution_id]["client_ids"] = [
            c.get("id") for c in selected_clients
        ]
        
        # Ensure FIO is installed on all clients (for FIO workloads)
        tool = workload_config.get("tool", "fio")
        if tool == "fio":
            logger.info(f"Ensuring FIO is installed on {len(selected_clients)} clients")
            fio_results = await self.workload_executor.ensure_fio_on_clients(selected_clients)
            
            fio_failed = []
            for client_id, success, message in fio_results:
                if not success:
                    logger.error(f"FIO setup failed on {client_id}: {message}")
                    fio_failed.append(client_id)
                else:
                    logger.info(f"FIO ready on {client_id}: {message}")
            
            if fio_failed:
                # Remove clients where FIO install failed
                selected_clients = [c for c in selected_clients if c.get("id") not in fio_failed]
                self.data_store.write_log(execution_id, f"FIO install failed on: {fio_failed}")
        
        # Check if this is a file workload that needs mounting
        storage_type = workload_config.get("storage_type", "block")
        mount_config = workload_config.get("mount")
        
        if storage_type == "file" and mount_config:
            # Check if we need to install ceph-common
            fs_type = mount_config.get("filesystem_type", "")
            if fs_type == "cephfs":
                # Get repo URL from cluster ceph config
                ceph_config = cluster_config.get("ceph", {})
                ceph_repo_url = ceph_config.get("repo_url")
                
                # Install ceph-common on all clients in parallel
                logger.info(f"Installing ceph-common on {len(selected_clients)} clients")
                install_tasks = [
                    self.workload_executor.install_ceph_common(client, ceph_repo_url)
                    for client in selected_clients
                ]
                results = await asyncio.gather(*install_tasks, return_exceptions=True)
                
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"Failed to install ceph-common on {selected_clients[i].get('id')}: {result}")
                    elif not result[0]:
                        logger.error(f"Failed to install ceph-common on {selected_clients[i].get('id')}: {result[1]}")
            
            # Mount filesystem on all clients in parallel
            logger.info(f"Mounting {mount_config.get('filesystem_type')} on {len(selected_clients)} clients")
            mount_tasks = [
                self.workload_executor.mount_filesystem(client, mount_config, cluster_config)
                for client in selected_clients
            ]
            mount_results = await asyncio.gather(*mount_tasks, return_exceptions=True)
            
            failed_mounts = []
            for i, result in enumerate(mount_results):
                client_id = selected_clients[i].get('id')
                if isinstance(result, Exception):
                    logger.error(f"Mount failed on {client_id}: {result}")
                    failed_mounts.append(client_id)
                elif not result[0]:
                    logger.error(f"Mount failed on {client_id}: {result[1]}")
                    failed_mounts.append(client_id)
                else:
                    logger.info(f"Mounted successfully on {client_id}")
            
            if failed_mounts:
                self.data_store.write_log(execution_id, f"Mount failed on clients: {failed_mounts}")
                # Remove failed clients
                self._active_executions[execution_id]["clients"] = [
                    c for c in selected_clients if c.get("id") not in failed_mounts
                ]
        
        await self.data_store.update_execution_status(
            execution_id,
            ExecutionStatus.PREPARING.value,
            client_count=len(self._active_executions[execution_id]["clients"]),
        )
        
        logger.info(f"Prepared {len(self._active_executions[execution_id]['clients'])} clients for execution: {execution_id}")
    
    async def _generate_client_configs(
        self,
        execution_id: str,
        workload_config: dict,
        clients: list[dict],
    ) -> dict[str, dict]:
        """Generate per-client workload configurations."""
        configs = {}
        
        io_config = workload_config.get("io", {})
        test_config = workload_config.get("test", {})
        
        for i, client in enumerate(clients):
            client_id = client.get("id")
            
            # Create client-specific config
            config = {
                "execution_id": execution_id,
                "client_id": client_id,
                "client_index": i,
                "total_clients": len(clients),
                "tool": workload_config.get("tool", "fio"),
                "io": io_config,
                "test": test_config,
                "cluster": workload_config.get("cluster_name"),
            }
            
            configs[client_id] = config
        
        return configs
    
    async def _run_execution_phase(
        self,
        execution_id: str,
        workload_config: dict,
        cluster_config: dict = None,
    ) -> None:
        """Run the main execution phase."""
        logger.info(f"Starting execution phase: {execution_id}")
        
        await self.data_store.update_execution_status(
            execution_id,
            ExecutionStatus.RUNNING.value,
        )
        self._update_state(execution_id, phase=ExecutionPhase.STEADY_STATE.value)
        
        # Get clients
        clients = self._active_executions[execution_id].get("clients", [])
        
        if not clients:
            raise Exception("No clients available for execution")
        
        # Determine workload type
        tool = workload_config.get("tool", "fio")
        
        if tool == "fill_cluster":
            # Fill cluster workload
            fill_config = workload_config.get("fill_cluster", {})
            logger.info(f"Running fill cluster on {len(clients)} clients")
            
            tasks = [
                self.workload_executor.run_fill_cluster(
                    client, fill_config, cluster_config or {}, execution_id
                )
                for client in clients
            ]
        else:
            # Standard FIO workload
            logger.info(f"Running FIO on {len(clients)} clients")
            
            tasks = [
                self.workload_executor.run_fio(client, workload_config, execution_id)
                for client in clients
            ]
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        total_iops = 0
        total_throughput = 0
        total_latency = 0
        latency_count = 0
        
        for i, result in enumerate(results):
            client_id = clients[i].get("id") if i < len(clients) else f"client_{i}"
            
            if isinstance(result, Exception):
                logger.error(f"FIO failed on {client_id}: {result}")
                self.data_store.write_log(execution_id, f"FIO failed on {client_id}: {result}")
                continue
            
            success, message, metrics = result
            
            if success and metrics:
                logger.info(f"FIO completed on {client_id}: {metrics.get('iops', {}).get('t', 0)} IOPS")
                
                # Aggregate metrics
                total_iops += metrics.get("iops", {}).get("t", 0)
                total_throughput += metrics.get("bw_mbps", {}).get("t", 0)
                if metrics.get("lat_us", {}).get("avg", 0) > 0:
                    total_latency += metrics.get("lat_us", {}).get("avg", 0)
                    latency_count += 1
                
                # Store per-client metrics
                client_metrics = {
                    "ts": datetime.utcnow().isoformat(),
                    "client_id": client_id,
                    **metrics,
                }
                self.data_store.append_client_metrics(execution_id, client_id, client_metrics)
            else:
                logger.warning(f"FIO issue on {client_id}: {message}")
                self.data_store.write_log(execution_id, f"FIO issue on {client_id}: {message}")
        
        # Calculate averages
        avg_latency = total_latency / latency_count if latency_count > 0 else 0
        
        # Store aggregated metrics
        aggregate_metrics = {
            "ts": datetime.utcnow().isoformat(),
            "iops": {"r": 0, "w": 0, "t": total_iops},
            "bw_mbps": {"r": 0, "w": 0, "t": total_throughput},
            "lat_us": {"avg": avg_latency, "p99": 0},
            "clients": len(clients),
        }
        self.data_store.append_metrics(execution_id, aggregate_metrics)
        
        # Update execution with final metrics
        await self.data_store.update_execution_status(
            execution_id,
            ExecutionStatus.RUNNING.value,
            total_iops=int(total_iops),
            total_throughput_mbps=total_throughput,
            avg_latency_us=avg_latency,
        )
        
        logger.info(f"FIO completed on all clients: {total_iops} total IOPS, {total_throughput:.1f} MB/s")
    
    async def _run_cleanup_phase(
        self,
        execution_id: str,
        workload_config: dict = None,
    ) -> None:
        """Clean up after execution."""
        logger.info(f"Cleaning up execution: {execution_id}")
        
        # Save command log
        command_log = self.workload_executor.get_command_log()
        if command_log:
            self.data_store.save_command_log(execution_id, command_log)
            self.workload_executor.clear_command_log()
        
        self._update_state(execution_id, phase=ExecutionPhase.CLEANUP.value)
        
        clients = self._active_executions[execution_id].get("clients", [])
        
        # Check if we need to unmount
        if workload_config:
            storage_type = workload_config.get("storage_type", "block")
            mount_config = workload_config.get("mount")
            
            if storage_type == "file" and mount_config and mount_config.get("auto_unmount", True):
                mount_point = mount_config.get("mount_point", "/mnt/scale_test")
                logger.info(f"Unmounting {mount_point} on {len(clients)} clients")
                
                # Unmount on all clients in parallel
                unmount_tasks = [
                    self.workload_executor.unmount_filesystem(client, mount_point)
                    for client in clients
                ]
                await asyncio.gather(*unmount_tasks, return_exceptions=True)
        
        # Clean up test files on all clients
        cleanup_tasks = [
            self.workload_executor.cleanup_client(
                client,
                mount_config.get("mount_point") if workload_config and workload_config.get("mount") else None
            )
            for client in clients
        ]
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        # Generate summary
        metrics = self.data_store.read_metrics(execution_id)
        
        # Calculate summary stats
        total_iops = 0
        total_throughput = 0
        total_latency = 0
        sample_count = 0
        
        for m in metrics:
            total_iops = max(total_iops, m.get("iops", {}).get("t", 0))
            total_throughput = max(total_throughput, m.get("bw_mbps", {}).get("t", 0))
            lat = m.get("lat_us", {}).get("avg", 0)
            if lat > 0:
                total_latency += lat
                sample_count += 1
        
        avg_latency = total_latency / sample_count if sample_count > 0 else 0
        
        summary = {
            "execution_id": execution_id,
            "completed_at": datetime.utcnow().isoformat(),
            "total_samples": len(metrics),
            "clients": [c.get("id") for c in clients],
            "client_count": len(clients),
            "peak_iops": int(total_iops),
            "peak_throughput_mbps": total_throughput,
            "avg_latency_us": avg_latency,
        }
        
        self.data_store.save_summary(execution_id, summary)
        
        self._update_state(execution_id, phase=ExecutionPhase.DONE.value)
    
    async def _handle_stopped(self, execution_id: str) -> None:
        """Handle a stopped execution."""
        await self.data_store.update_execution_status(
            execution_id,
            ExecutionStatus.CANCELLED.value,
        )
        
        # Send stop to all clients
        clients = self._active_executions.get(execution_id, {}).get("clients", [])
        for client_id in clients:
            event = create_execution_stop_event(execution_id, client_id)
            await self.redis_client.publish_to_agent(client_id, event)
        
        self._cleanup_execution(execution_id)
    
    def _update_state(self, execution_id: str, **kwargs) -> None:
        """Update execution state."""
        if execution_id in self._active_executions:
            self._active_executions[execution_id].update(kwargs)
    
    def _cleanup_execution(self, execution_id: str) -> None:
        """Clean up execution state."""
        self._active_executions.pop(execution_id, None)
        self._stop_flags.pop(execution_id, None)
        self._pause_flags.pop(execution_id, None)
    
    def get_execution_state(self, execution_id: str) -> Optional[dict]:
        """Get current execution state."""
        return self._active_executions.get(execution_id)
    
    async def stop_execution(self, execution_id: str) -> None:
        """Signal an execution to stop."""
        self._stop_flags[execution_id] = True
        logger.info(f"Stop signal sent for execution: {execution_id}")
    
    async def pause_execution(self, execution_id: str) -> None:
        """Signal an execution to pause."""
        self._pause_flags[execution_id] = True
        await self.data_store.update_execution_status(
            execution_id,
            ExecutionStatus.PAUSED.value,
        )
        logger.info(f"Pause signal sent for execution: {execution_id}")
    
    async def resume_execution(self, execution_id: str) -> None:
        """Signal an execution to resume."""
        self._pause_flags[execution_id] = False
        await self.data_store.update_execution_status(
            execution_id,
            ExecutionStatus.RUNNING.value,
        )
        logger.info(f"Resume signal sent for execution: {execution_id}")
    
    async def scale_up(
        self,
        execution_id: str,
        count: int = None,
        client_ids: list[str] = None,
    ) -> dict:
        """Add clients to a running execution."""
        state = self._active_executions.get(execution_id)
        if not state:
            return {"error": "Execution not found"}
        
        # Get available clients
        all_clients = await self.data_store.get_clients()
        current_clients = set(state.get("clients", []))
        
        available = [
            c for c in all_clients
            if c.get("id") not in current_clients
            and c.get("status") == "online"
        ]
        
        if client_ids:
            to_add = [c for c in available if c.get("id") in client_ids]
        elif count:
            to_add = available[:count]
        else:
            return {"error": "Specify count or client_ids"}
        
        # Add clients
        added = []
        for client in to_add:
            client_id = client.get("id")
            current_clients.add(client_id)
            added.append(client_id)
            
            # Send start command
            event = create_execution_start_event(
                execution_id=execution_id,
                target=client_id,
                config={},
            )
            await self.redis_client.publish_to_agent(client_id, event)
        
        state["clients"] = list(current_clients)
        
        return {
            "message": f"Added {len(added)} clients",
            "added": added,
            "total_clients": len(current_clients),
        }
    
    async def scale_down(
        self,
        execution_id: str,
        count: int = None,
        client_ids: list[str] = None,
    ) -> dict:
        """Remove clients from a running execution."""
        state = self._active_executions.get(execution_id)
        if not state:
            return {"error": "Execution not found"}
        
        current_clients = list(state.get("clients", []))
        
        if client_ids:
            to_remove = [c for c in client_ids if c in current_clients]
        elif count:
            to_remove = current_clients[-count:]
        else:
            return {"error": "Specify count or client_ids"}
        
        # Remove clients
        removed = []
        for client_id in to_remove:
            if client_id in current_clients:
                current_clients.remove(client_id)
                removed.append(client_id)
                
                # Send stop command
                event = create_execution_stop_event(execution_id, client_id)
                await self.redis_client.publish_to_agent(client_id, event)
        
        state["clients"] = current_clients
        
        return {
            "message": f"Removed {len(removed)} clients",
            "removed": removed,
            "total_clients": len(current_clients),
        }
