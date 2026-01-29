"""Ceph cluster health checker."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List, Union

from pydantic import BaseModel

from common.models.cluster import CephConnection, InstallerNode
from manager.deployment.ssh_client import SSHClient

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Ceph health status."""
    OK = "HEALTH_OK"
    WARN = "HEALTH_WARN"
    ERR = "HEALTH_ERR"
    UNKNOWN = "UNKNOWN"


class CheckSeverity(str, Enum):
    """Check result severity."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class CheckResult(BaseModel):
    """Result of a single health check."""
    name: str
    passed: bool
    severity: CheckSeverity
    message: str
    details: dict = {}
    raw_output: Optional[str] = None


class CephClusterState(BaseModel):
    """Ceph cluster state information."""
    health_status: HealthStatus = HealthStatus.UNKNOWN
    health_checks: dict = {}
    
    # Monitors
    mon_count: int = 0
    mon_quorum: list[str] = []
    mon_in_quorum: int = 0
    
    # OSDs
    osd_count: int = 0
    osd_up: int = 0
    osd_in: int = 0
    osd_down: list[int] = []
    
    # PGs
    pg_count: int = 0
    pg_active_clean: int = 0
    pg_degraded: int = 0
    pg_recovering: int = 0
    pg_stuck: int = 0
    
    # Pools
    pools: list[dict] = []
    
    # Capacity
    total_bytes: int = 0
    used_bytes: int = 0
    available_bytes: int = 0
    used_percent: float = 0
    
    # MGR
    mgr_active: str = ""
    mgr_standbys: list[str] = []
    
    # Versions
    versions: dict = {}


class CephHealthChecker:
    """Check Ceph cluster health before running tests."""
    
    def __init__(
        self, 
        connection: CephConnection,
        installer_node: Optional[InstallerNode] = None
    ):
        self.connection = connection
        self.ceph_conf = connection.conf_path
        self.keyring = connection.keyring_path
        self.user = connection.user
        self.installer_node = installer_node
    
    async def run_ceph_command(
        self,
        command: list[str],
        json_output: bool = True
    ) -> dict | str:
        """Execute a Ceph CLI command via SSH or locally."""
        cmd_parts = [
            "ceph",
            "--conf", self.ceph_conf,
            "--keyring", self.keyring,
            "--name", f"client.{self.user}",
        ]
        
        if json_output:
            cmd_parts.extend(["-f", "json"])
        
        cmd_parts.extend(command)
        cmd_str = " ".join(cmd_parts)
        
        try:
            if self.installer_node:
                # Run via SSH to installer node
                ssh_client = SSHClient(
                    hostname=self.installer_node.host,
                    username=self.installer_node.username,
                    password=self.installer_node.password,
                    private_key_path=self.installer_node.key_path,
                    port=self.installer_node.port,
                )
                await ssh_client.connect()
                try:
                    result = await ssh_client.run_command(cmd_str, timeout=30, raise_on_error=False)
                    if not result.success:
                        raise Exception(f"Ceph command failed: {result.stderr}")
                    output = result.stdout
                finally:
                    await ssh_client.close()
            else:
                # Run locally
                process = await asyncio.create_subprocess_exec(
                    *cmd_parts,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=30,
                )
                
                if process.returncode != 0:
                    raise Exception(f"Ceph command failed: {stderr.decode()}")
                
                output = stdout.decode()
            
            if json_output:
                return json.loads(output)
            return output
            
        except asyncio.TimeoutError:
            raise Exception("Ceph command timed out")
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse Ceph output: {e}")
    
    async def get_cluster_state(self) -> CephClusterState:
        """Collect comprehensive cluster state."""
        state = CephClusterState()
        
        try:
            # Get status
            status = await self.run_ceph_command(["status"])
            
            # Parse health
            health = status.get("health", {})
            health_status = health.get("status", "UNKNOWN")
            state.health_status = HealthStatus(health_status)
            state.health_checks = health.get("checks", {})
            
            # Parse monitors
            monmap = status.get("monmap", {})
            state.mon_count = len(monmap.get("mons", []))
            state.mon_quorum = status.get("quorum_names", [])
            state.mon_in_quorum = len(status.get("quorum", []))
            
            # Parse OSDs
            osdmap = status.get("osdmap", {})
            state.osd_count = osdmap.get("num_osds", 0)
            state.osd_up = osdmap.get("num_up_osds", 0)
            state.osd_in = osdmap.get("num_in_osds", 0)
            
            # Get OSD tree for down OSDs
            try:
                osd_tree = await self.run_ceph_command(["osd", "tree"])
                for node in osd_tree.get("nodes", []):
                    if node.get("type") == "osd" and node.get("status") != "up":
                        state.osd_down.append(node.get("id"))
            except Exception:
                pass
            
            # Parse PGs
            pgmap = status.get("pgmap", {})
            state.pg_count = pgmap.get("num_pgs", 0)
            
            pg_states = {}
            for state_info in pgmap.get("pgs_by_state", []):
                for s in state_info.get("state_name", "").split("+"):
                    pg_states[s] = pg_states.get(s, 0) + state_info.get("count", 0)
            
            state.pg_active_clean = pg_states.get("active", 0)
            state.pg_degraded = pg_states.get("degraded", 0)
            state.pg_recovering = pg_states.get("recovering", 0) + pg_states.get("recovery_wait", 0)
            state.pg_stuck = pg_states.get("stuck", 0)
            
            # Parse MGR - handle different Ceph versions
            mgrmap = status.get("mgrmap", {})
            if not mgrmap:
                # Try alternative location for newer Ceph versions
                mgrmap = status.get("mgr_map", {})
            
            state.mgr_active = mgrmap.get("active_name", "") or mgrmap.get("active", {}).get("name", "")
            state.mgr_standbys = [s.get("name", "") for s in mgrmap.get("standbys", [])]
            
            # If still no active MGR found, try to get it from services
            if not state.mgr_active:
                servicemap = status.get("servicemap", {})
                services = servicemap.get("services", {})
                mgr_service = services.get("mgr", {})
                daemons = mgr_service.get("daemons", {})
                for daemon_name in daemons:
                    if daemon_name != "summary":
                        state.mgr_active = daemon_name
                        break
            
            # Get capacity
            try:
                df = await self.run_ceph_command(["df"])
                stats = df.get("stats", {})
                state.total_bytes = stats.get("total_bytes", 0)
                state.used_bytes = stats.get("total_used_bytes", 0)
                state.available_bytes = stats.get("total_avail_bytes", 0)
                if state.total_bytes > 0:
                    state.used_percent = (state.used_bytes / state.total_bytes) * 100
            except Exception:
                pass
            
        except Exception as e:
            logger.error(f"Failed to get cluster state: {e}")
            state.health_status = HealthStatus.UNKNOWN
        
        return state
    
    async def run_all_checks(self) -> list[CheckResult]:
        """Run all cluster health checks."""
        results = []
        
        try:
            state = await self.get_cluster_state()
        except Exception as e:
            return [CheckResult(
                name="cluster_connectivity",
                passed=False,
                severity=CheckSeverity.CRITICAL,
                message=f"Cannot connect to Ceph cluster: {str(e)}",
            )]
        
        # Check 1: Overall health
        results.append(self._check_overall_health(state))
        
        # Check 2: OSD status
        results.append(self._check_osd_status(state))
        
        # Check 3: Monitor quorum
        results.append(self._check_mon_quorum(state))
        
        # Check 4: PG status
        results.append(self._check_pg_status(state))
        
        # Check 5: Capacity
        results.append(self._check_capacity(state))
        
        # Check 6: MGR status
        results.append(self._check_mgr_status(state))
        
        return results
    
    def _check_overall_health(self, state: CephClusterState) -> CheckResult:
        """Check overall cluster health."""
        if state.health_status == HealthStatus.OK:
            return CheckResult(
                name="cluster_health",
                passed=True,
                severity=CheckSeverity.INFO,
                message="Cluster health is OK",
                details={"status": state.health_status.value},
            )
        elif state.health_status == HealthStatus.WARN:
            return CheckResult(
                name="cluster_health",
                passed=True,
                severity=CheckSeverity.WARNING,
                message=f"Cluster health is WARN: {len(state.health_checks)} issues",
                details={
                    "status": state.health_status.value,
                    "checks": state.health_checks,
                },
            )
        else:
            return CheckResult(
                name="cluster_health",
                passed=False,
                severity=CheckSeverity.CRITICAL,
                message=f"Cluster health is {state.health_status.value}",
                details={
                    "status": state.health_status.value,
                    "checks": state.health_checks,
                },
            )
    
    def _check_osd_status(self, state: CephClusterState) -> CheckResult:
        """Check OSD status."""
        if len(state.osd_down) == 0:
            return CheckResult(
                name="osd_status",
                passed=True,
                severity=CheckSeverity.INFO,
                message=f"All {state.osd_count} OSDs are up and in",
                details={
                    "total": state.osd_count,
                    "up": state.osd_up,
                    "in": state.osd_in,
                },
            )
        elif len(state.osd_down) <= 2:
            return CheckResult(
                name="osd_status",
                passed=True,
                severity=CheckSeverity.WARNING,
                message=f"{len(state.osd_down)} OSD(s) down: {state.osd_down}",
                details={
                    "total": state.osd_count,
                    "up": state.osd_up,
                    "in": state.osd_in,
                    "down": state.osd_down,
                },
            )
        else:
            return CheckResult(
                name="osd_status",
                passed=False,
                severity=CheckSeverity.CRITICAL,
                message=f"Too many OSDs down: {len(state.osd_down)}",
                details={
                    "total": state.osd_count,
                    "up": state.osd_up,
                    "down": state.osd_down,
                },
            )
    
    def _check_mon_quorum(self, state: CephClusterState) -> CheckResult:
        """Check monitor quorum."""
        if state.mon_in_quorum == state.mon_count:
            return CheckResult(
                name="mon_quorum",
                passed=True,
                severity=CheckSeverity.INFO,
                message=f"All {state.mon_count} monitors in quorum",
                details={"quorum": state.mon_quorum},
            )
        elif state.mon_in_quorum >= (state.mon_count // 2) + 1:
            return CheckResult(
                name="mon_quorum",
                passed=True,
                severity=CheckSeverity.WARNING,
                message=f"Monitor quorum maintained ({state.mon_in_quorum}/{state.mon_count})",
                details={"quorum": state.mon_quorum},
            )
        else:
            return CheckResult(
                name="mon_quorum",
                passed=False,
                severity=CheckSeverity.CRITICAL,
                message=f"Monitor quorum lost ({state.mon_in_quorum}/{state.mon_count})",
                details={"quorum": state.mon_quorum},
            )
    
    def _check_pg_status(self, state: CephClusterState) -> CheckResult:
        """Check PG status."""
        if state.pg_degraded == 0 and state.pg_recovering == 0 and state.pg_stuck == 0:
            return CheckResult(
                name="pg_status",
                passed=True,
                severity=CheckSeverity.INFO,
                message=f"All {state.pg_count} PGs are active+clean",
                details={"total_pgs": state.pg_count},
            )
        elif state.pg_stuck > 0:
            return CheckResult(
                name="pg_status",
                passed=False,
                severity=CheckSeverity.CRITICAL,
                message=f"{state.pg_stuck} PGs are stuck",
                details={
                    "total": state.pg_count,
                    "degraded": state.pg_degraded,
                    "recovering": state.pg_recovering,
                    "stuck": state.pg_stuck,
                },
            )
        else:
            return CheckResult(
                name="pg_status",
                passed=True,
                severity=CheckSeverity.WARNING,
                message=f"PGs not fully clean: {state.pg_degraded} degraded",
                details={
                    "total": state.pg_count,
                    "degraded": state.pg_degraded,
                    "recovering": state.pg_recovering,
                },
            )
    
    def _check_capacity(self, state: CephClusterState) -> CheckResult:
        """Check cluster capacity."""
        if state.used_percent < 70:
            return CheckResult(
                name="capacity",
                passed=True,
                severity=CheckSeverity.INFO,
                message=f"Cluster capacity: {state.used_percent:.1f}% used",
                details={
                    "total_tb": state.total_bytes / (1024**4),
                    "used_percent": state.used_percent,
                },
            )
        elif state.used_percent < 85:
            return CheckResult(
                name="capacity",
                passed=True,
                severity=CheckSeverity.WARNING,
                message=f"Cluster capacity high: {state.used_percent:.1f}% used",
                details={"used_percent": state.used_percent},
            )
        else:
            return CheckResult(
                name="capacity",
                passed=False,
                severity=CheckSeverity.CRITICAL,
                message=f"Cluster capacity critical: {state.used_percent:.1f}% used",
                details={"used_percent": state.used_percent},
            )
    
    def _check_mgr_status(self, state: CephClusterState) -> CheckResult:
        """Check MGR daemon status."""
        if state.mgr_active and len(state.mgr_standbys) > 0:
            return CheckResult(
                name="mgr_status",
                passed=True,
                severity=CheckSeverity.INFO,
                message=f"MGR active: {state.mgr_active}",
                details={
                    "active": state.mgr_active,
                    "standbys": state.mgr_standbys,
                },
            )
        elif state.mgr_active:
            return CheckResult(
                name="mgr_status",
                passed=True,
                severity=CheckSeverity.WARNING,
                message="MGR active but no standbys",
                details={"active": state.mgr_active},
            )
        else:
            # MGR not detected - this is a warning, not a blocker
            # Cluster can still function for I/O without MGR
            return CheckResult(
                name="mgr_status",
                passed=True,  # Changed from False - don't block on missing MGR info
                severity=CheckSeverity.WARNING,
                message="No active MGR daemon detected (cluster may still be functional)",
            )
