"""Precheck runner - orchestrates all pre-test validations."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, List, Dict

from pydantic import BaseModel, Field

from common.models.cluster import ClusterConfig, StorageBackend
from common.models.client import ClientStatus
from common.models.execution import PrecheckReport
from manager.prechecks.cluster.ceph import CephHealthChecker, CheckResult, CheckSeverity
from manager.prechecks.cluster.custom_commands import CustomCommandRunner, CustomCommandConfig
from manager.prechecks.client.connectivity import ClientHealthChecker, ClientHealthResult

logger = logging.getLogger(__name__)


class PrecheckRunner:
    """Orchestrate all prechecks before test execution."""
    
    def __init__(
        self,
        cluster_config: ClusterConfig,
        clients: list[dict],
        check_cluster: bool = True,
        check_clients: bool = True,
        check_network: bool = False,
        custom_commands: list[dict] = None,
    ):
        self.cluster_config = cluster_config
        self.clients = clients
        self.check_cluster = check_cluster
        self.check_clients = check_clients
        self.check_network = check_network
        self.custom_commands = custom_commands or []
    
    async def run_all_prechecks(self, execution_id: str) -> PrecheckReport:
        """Run all prechecks and generate report."""
        started_at = datetime.utcnow()
        
        blocking_issues = []
        warnings = []
        cluster_checks = []
        cluster_health = None
        client_results = []
        excluded_clients = []
        custom_command_results = []
        network_baseline = None
        
        # Phase 1: Cluster Health
        if self.check_cluster:
            logger.info("Phase 1: Checking cluster health...")
            
            if self.cluster_config.backend in [StorageBackend.CEPH_RBD, StorageBackend.CEPHFS]:
                checker = CephHealthChecker(
                    self.cluster_config.ceph,
                    installer_node=self.cluster_config.installer_node
                )
                
                try:
                    state = await checker.get_cluster_state()
                    cluster_health = state.health_status.value
                    cluster_checks = await checker.run_all_checks()
                    
                    for check in cluster_checks:
                        if not check.passed:
                            blocking_issues.append(f"[Cluster] {check.name}: {check.message}")
                        elif check.severity == CheckSeverity.WARNING:
                            warnings.append(f"[Cluster] {check.name}: {check.message}")
                            
                except Exception as e:
                    logger.error(f"Cluster health check failed: {e}")
                    blocking_issues.append(f"[Cluster] Connection failed: {e}")
        
        # Phase 2: Custom Commands
        if self.custom_commands:
            logger.info("Phase 2: Running custom commands...")
            
            ceph_conf = "/etc/ceph/ceph.conf"
            if self.cluster_config.ceph:
                ceph_conf = self.cluster_config.ceph.conf_path
            
            runner = CustomCommandRunner(ceph_conf=ceph_conf)
            
            configs = [
                CustomCommandConfig(**cmd) if isinstance(cmd, dict) else cmd
                for cmd in self.custom_commands
            ]
            
            results = await runner.run_multiple(configs)
            custom_command_results = [r.model_dump() for r in results]
            
            for result in results:
                if not result.success and result.blocking:
                    blocking_issues.append(f"[Command] {result.command}: {result.stderr}")
        
        # Phase 3: Client Health
        clients_online = 0
        clients_total = len(self.clients)
        
        if self.check_clients and self.clients:
            logger.info("Phase 3: Checking client health...")
            
            # Get SSH config from first client as default
            first_client = self.clients[0] if self.clients else {}
            
            checker = ClientHealthChecker(
                ssh_user=first_client.get("ssh_user", "root"),
                ssh_key_path=first_client.get("ssh_key_path"),
                ssh_password=first_client.get("ssh_password"),
            )
            
            # Get storage endpoint
            storage_endpoint = ""
            if self.cluster_config.ceph and self.cluster_config.ceph.monitors:
                storage_endpoint = self.cluster_config.ceph.monitors[0].split(":")[0]
            
            # Check all clients
            client_list = [
                {"id": c.get("id"), "hostname": c.get("hostname")}
                for c in self.clients
            ]
            
            results = await checker.check_all_clients(
                clients=client_list,
                storage_endpoint=storage_endpoint,
                mount_points=[],
            )
            
            client_results = [r.model_dump() for r in results]
            
            for result in results:
                if result.status == ClientStatus.ONLINE:
                    clients_online += 1
                else:
                    excluded_clients.append(result.client_id)
                    if result.status == ClientStatus.UNREACHABLE:
                        warnings.append(
                            f"[Client] {result.hostname}: unreachable - {', '.join(result.errors)}"
                        )
                    else:
                        warnings.append(
                            f"[Client] {result.hostname}: {result.status.value}"
                        )
        
        # Phase 4: Network Baseline (optional)
        if self.check_network:
            logger.info("Phase 4: Network baseline check...")
            # TODO: Implement network baseline checks
            network_baseline = {"message": "Not implemented"}
        
        # Calculate summary
        completed_at = datetime.utcnow()
        duration = (completed_at - started_at).total_seconds()
        
        # Determine overall status
        if blocking_issues:
            overall_status = "failed"
            can_proceed = False
            proceed_message = f"Cannot proceed: {len(blocking_issues)} critical issue(s)"
        elif warnings:
            overall_status = "passed_with_warnings"
            can_proceed = True
            proceed_message = f"Can proceed with {len(warnings)} warning(s)"
        else:
            overall_status = "passed"
            can_proceed = True
            proceed_message = "All checks passed. Ready to proceed."
        
        # Create report
        report = PrecheckReport(
            execution_id=execution_id,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            overall_status=overall_status,
            can_proceed=can_proceed,
            cluster_health=cluster_health,
            cluster_checks=[c.model_dump() for c in cluster_checks],
            clients_total=clients_total,
            clients_online=clients_online,
            clients_offline=clients_total - clients_online,
            client_results=client_results,
            excluded_clients=excluded_clients,
            custom_command_results=custom_command_results,
            network_baseline=network_baseline,
            warnings=warnings,
            blocking_issues=blocking_issues,
            proceed_message=proceed_message,
        )
        
        logger.info(f"Prechecks completed: {overall_status}")
        return report
