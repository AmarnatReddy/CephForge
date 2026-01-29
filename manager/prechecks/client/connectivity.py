"""Client connectivity and health checker."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Optional, List, Dict, Tuple

from pydantic import BaseModel, Field

from common.models.client import ClientStatus

logger = logging.getLogger(__name__)


class ClientHealthResult(BaseModel):
    """Client health check result."""
    client_id: str
    hostname: str
    ip_address: str = ""
    status: ClientStatus = ClientStatus.UNKNOWN
    
    # Connectivity
    ssh_reachable: bool = False
    ssh_latency_ms: Optional[float] = None
    
    # Agent
    agent_running: bool = False
    agent_version: Optional[str] = None
    agent_pid: Optional[int] = None
    
    # System
    uptime_seconds: Optional[int] = None
    load_average: Optional[tuple] = None
    memory_total_gb: Optional[float] = None
    memory_available_gb: Optional[float] = None
    disk_space_gb: Optional[float] = None
    
    # Tools
    tools_installed: dict[str, bool] = Field(default_factory=dict)
    
    # Storage
    storage_accessible: bool = False
    mount_points: list[dict] = Field(default_factory=list)
    
    # Network
    network_to_storage_ms: Optional[float] = None
    
    # Errors
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    
    @property
    def is_healthy(self) -> bool:
        """Check if client passed all critical health checks."""
        return (
            self.ssh_reachable
            and self.agent_running
            and len(self.errors) == 0
        )


class ClientHealthChecker:
    """Check health of client nodes."""
    
    REQUIRED_TOOLS = ["fio", "iperf3", "dd", "iostat", "ping"]
    
    def __init__(
        self,
        ssh_user: str = "root",
        ssh_key_path: Optional[str] = None,
        ssh_password: Optional[str] = None,
        ssh_timeout: int = 10,
        agent_port: int = 8080,
    ):
        self.ssh_user = ssh_user
        self.ssh_key_path = ssh_key_path
        self.ssh_password = ssh_password
        self.ssh_timeout = ssh_timeout
        self.agent_port = agent_port
    
    async def check_single_client(
        self,
        client_id: str,
        hostname: str,
        storage_endpoint: str = "",
        mount_points: list[str] = None,
    ) -> ClientHealthResult:
        """Check health of a single client."""
        mount_points = mount_points or []
        errors = []
        warnings = []
        
        result = ClientHealthResult(
            client_id=client_id,
            hostname=hostname,
            ip_address=hostname,
            status=ClientStatus.UNKNOWN,
            errors=errors,
            warnings=warnings,
        )
        
        try:
            import asyncssh
            
            # Connect via SSH
            start = time.time()
            
            conn_kwargs = {
                "host": hostname,
                "username": self.ssh_user,
                "known_hosts": None,
                "connect_timeout": self.ssh_timeout,
            }
            
            if self.ssh_key_path:
                conn_kwargs["client_keys"] = [self.ssh_key_path]
            elif self.ssh_password:
                conn_kwargs["password"] = self.ssh_password
            
            async with asyncssh.connect(**conn_kwargs) as conn:
                result.ssh_reachable = True
                result.ssh_latency_ms = (time.time() - start) * 1000
                
                # Check agent status
                agent_check = await conn.run(
                    f"curl -s --connect-timeout 5 http://localhost:{self.agent_port}/health || echo 'AGENT_DOWN'",
                    check=False,
                )
                
                if agent_check.returncode == 0 and "AGENT_DOWN" not in agent_check.stdout:
                    result.agent_running = True
                    try:
                        import json
                        health = json.loads(agent_check.stdout)
                        result.agent_version = health.get("version")
                        result.agent_pid = health.get("pid")
                    except Exception:
                        pass
                else:
                    result.agent_running = False
                    errors.append("Agent not running or not responding")
                
                # Get system info
                sys_info = await conn.run(
                    "cat /proc/uptime 2>/dev/null && "
                    "cat /proc/loadavg 2>/dev/null && "
                    "free -b 2>/dev/null | grep Mem && "
                    "df -B1 / 2>/dev/null | tail -1",
                    check=False,
                )
                
                if sys_info.returncode == 0:
                    lines = sys_info.stdout.strip().split('\n')
                    try:
                        if len(lines) >= 1:
                            result.uptime_seconds = int(float(lines[0].split()[0]))
                        if len(lines) >= 2:
                            load = lines[1].split()[:3]
                            result.load_average = (float(load[0]), float(load[1]), float(load[2]))
                        if len(lines) >= 3:
                            mem = lines[2].split()
                            result.memory_total_gb = int(mem[1]) / (1024**3)
                            result.memory_available_gb = int(mem[6]) / (1024**3) if len(mem) > 6 else 0
                        if len(lines) >= 4:
                            disk = lines[3].split()
                            result.disk_space_gb = int(disk[3]) / (1024**3) if len(disk) > 3 else 0
                    except Exception:
                        pass
                
                # Check required tools
                for tool in self.REQUIRED_TOOLS:
                    tool_check = await conn.run(f"which {tool}", check=False)
                    result.tools_installed[tool] = tool_check.returncode == 0
                    if not result.tools_installed[tool]:
                        if tool == "fio":
                            # FIO is critical - will be auto-installed during execution
                            warnings.append(f"FIO not installed (will be auto-installed during execution)")
                        else:
                            warnings.append(f"Tool '{tool}' not installed")
                
                # Check mount points
                for mp in mount_points:
                    mp_check = await conn.run(
                        f"mountpoint -q {mp} 2>/dev/null && ls {mp} > /dev/null 2>&1",
                        check=False,
                    )
                    accessible = mp_check.returncode == 0
                    result.mount_points.append({
                        "path": mp,
                        "accessible": accessible,
                    })
                    if accessible:
                        result.storage_accessible = True
                    else:
                        errors.append(f"Mount point '{mp}' not accessible")
                
                # Check network to storage
                if storage_endpoint:
                    ping_check = await conn.run(
                        f"ping -c 3 -q {storage_endpoint} 2>/dev/null | tail -1",
                        check=False,
                    )
                    if ping_check.returncode == 0:
                        try:
                            match = re.search(r'= [\d.]+/([\d.]+)/', ping_check.stdout)
                            if match:
                                result.network_to_storage_ms = float(match.group(1))
                        except Exception:
                            pass
                
                # Determine final status
                if not result.agent_running:
                    result.status = ClientStatus.ERROR
                elif errors:
                    result.status = ClientStatus.ERROR
                else:
                    result.status = ClientStatus.ONLINE
                
        except asyncssh.PermissionDenied:
            result.status = ClientStatus.UNREACHABLE
            errors.append("SSH authentication failed")
        except asyncssh.ConnectionLost:
            result.status = ClientStatus.UNREACHABLE
            errors.append("SSH connection lost")
        except (OSError, asyncio.TimeoutError) as e:
            result.status = ClientStatus.UNREACHABLE
            errors.append(f"Cannot reach client: {e}")
        except Exception as e:
            result.status = ClientStatus.OFFLINE
            errors.append(str(e))
        
        result.errors = errors
        result.warnings = warnings
        return result
    
    async def check_all_clients(
        self,
        clients: list[dict],
        storage_endpoint: str = "",
        mount_points: list[str] = None,
    ) -> list[ClientHealthResult]:
        """Check all clients in parallel."""
        mount_points = mount_points or []
        
        tasks = [
            self.check_single_client(
                client["id"],
                client["hostname"],
                storage_endpoint,
                mount_points,
            )
            for client in clients
        ]
        
        return await asyncio.gather(*tasks)
    
    def generate_summary(self, results: list[ClientHealthResult]) -> dict:
        """Generate summary of client health checks."""
        total = len(results)
        online = sum(1 for r in results if r.status == ClientStatus.ONLINE)
        
        failed_clients = [
            {
                "id": r.client_id,
                "hostname": r.hostname,
                "status": r.status.value,
                "errors": r.errors,
            }
            for r in results if r.status != ClientStatus.ONLINE
        ]
        
        return {
            "total_clients": total,
            "online": online,
            "offline": total - online,
            "all_healthy": online == total,
            "failed_clients": failed_clients,
        }
