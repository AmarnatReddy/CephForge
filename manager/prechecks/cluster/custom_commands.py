"""Custom command runner for pre-test commands."""

from __future__ import annotations

import asyncio
import logging
import shlex
import time
from dataclasses import dataclass
from typing import Optional, List, Dict

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CustomCommandConfig(BaseModel):
    """Configuration for a custom command."""
    command: str
    description: str = ""
    blocking: bool = False
    expected_exit_code: int = 0
    timeout: int = 60
    capture_for_report: bool = True


class CommandResult(BaseModel):
    """Result of executing a custom command."""
    command: str
    description: str
    exit_code: int
    stdout: str
    stderr: str
    success: bool
    duration_ms: float
    blocking: bool


class CustomCommandRunner:
    """Run user-defined commands before tests."""
    
    # Pre-built useful commands for Ceph
    COMMON_CEPH_COMMANDS = {
        "cluster_status": CustomCommandConfig(
            command="ceph status",
            description="Get cluster status",
        ),
        "osd_tree": CustomCommandConfig(
            command="ceph osd tree",
            description="Show OSD tree",
        ),
        "pool_list": CustomCommandConfig(
            command="ceph osd pool ls detail",
            description="List all pools with details",
        ),
        "df": CustomCommandConfig(
            command="ceph df",
            description="Cluster disk usage",
        ),
        "pg_stat": CustomCommandConfig(
            command="ceph pg stat",
            description="PG statistics",
        ),
        "osd_perf": CustomCommandConfig(
            command="ceph osd perf",
            description="OSD performance stats",
        ),
        "health_detail": CustomCommandConfig(
            command="ceph health detail",
            description="Detailed health information",
        ),
        "mon_stat": CustomCommandConfig(
            command="ceph mon stat",
            description="Monitor status",
        ),
    }
    
    def __init__(self, ceph_conf: str = "/etc/ceph/ceph.conf"):
        self.ceph_conf = ceph_conf
    
    async def run_command(self, config: CustomCommandConfig) -> CommandResult:
        """Run a single custom command."""
        start_time = time.time()
        
        try:
            # Parse command
            cmd_parts = shlex.split(config.command)
            
            # Add ceph config if it's a ceph command
            if cmd_parts and cmd_parts[0] == "ceph":
                cmd_parts.insert(1, "--conf")
                cmd_parts.insert(2, self.ceph_conf)
            
            # Run command
            process = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=config.timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                return CommandResult(
                    command=config.command,
                    description=config.description,
                    exit_code=-1,
                    stdout="",
                    stderr=f"Command timed out after {config.timeout}s",
                    success=False,
                    duration_ms=config.timeout * 1000,
                    blocking=config.blocking,
                )
            
            duration_ms = (time.time() - start_time) * 1000
            
            return CommandResult(
                command=config.command,
                description=config.description,
                exit_code=process.returncode,
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                success=process.returncode == config.expected_exit_code,
                duration_ms=duration_ms,
                blocking=config.blocking,
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return CommandResult(
                command=config.command,
                description=config.description,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                success=False,
                duration_ms=duration_ms,
                blocking=config.blocking,
            )
    
    async def run_multiple(self, commands: list[CustomCommandConfig]) -> list[CommandResult]:
        """Run multiple commands sequentially."""
        results = []
        
        for cmd in commands:
            result = await self.run_command(cmd)
            results.append(result)
            
            # Stop if blocking command failed
            if cmd.blocking and not result.success:
                logger.warning(f"Blocking command failed: {cmd.command}")
                break
        
        return results
    
    async def run_preset(self, preset_name: str) -> CommandResult:
        """Run a preset command."""
        if preset_name not in self.COMMON_CEPH_COMMANDS:
            raise ValueError(f"Unknown preset: {preset_name}")
        
        return await self.run_command(self.COMMON_CEPH_COMMANDS[preset_name])
    
    async def run_all_presets(self) -> list[CommandResult]:
        """Run all preset commands for baseline capture."""
        results = []
        for name, config in self.COMMON_CEPH_COMMANDS.items():
            try:
                result = await self.run_command(config)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to run preset {name}: {e}")
        return results
