"""Deploy and manage agents on client nodes via SSH."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DeploymentStatus(str, Enum):
    """Agent deployment status."""
    PENDING = "pending"
    CONNECTING = "connecting"
    COPYING = "copying"
    INSTALLING = "installing"
    STARTING = "starting"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class DeploymentResult:
    """Result of agent deployment."""
    client_id: str
    hostname: str
    status: DeploymentStatus
    message: str = ""
    agent_port: int = 8080


class AgentDeployer:
    """Deploy agent to client nodes via SSH."""
    
    # Agent files to copy
    AGENT_FILES = [
        "agent/__init__.py",
        "agent/main.py",
        "agent/config.py",
        "agent/core/__init__.py",
        "agent/core/executor.py",
        "agent/core/reporter.py",
        "agent/network/__init__.py",
        "agent/network/profiler.py",
        "common/__init__.py",
        "common/utils.py",
        "common/models/__init__.py",
        "common/models/client.py",
        "common/models/cluster.py",
        "common/models/execution.py",
        "common/models/metrics.py",
        "common/models/workload.py",
        "common/messaging/__init__.py",
        "common/messaging/events.py",
        "common/messaging/redis_client.py",
    ]
    
    # Requirements for agent
    AGENT_REQUIREMENTS = [
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "pydantic>=2.5.0",
        "pydantic-settings>=2.1.0",
        "redis>=5.0.0",
        "aiofiles>=23.2.0",
        "psutil>=5.9.0",
        "PyYAML>=6.0.0",
    ]
    
    def __init__(
        self,
        manager_host: str = "localhost",
        manager_port: int = 8000,
        redis_host: str = "localhost",
        redis_port: int = 6379,
    ):
        self.manager_host = manager_host
        self.manager_port = manager_port
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.base_path = Path(__file__).parent.parent.parent  # scale_framework root
    
    async def _run_ssh_command(
        self,
        host: str,
        username: str,
        command: str,
        password: Optional[str] = None,
        key_path: Optional[str] = None,
        port: int = 22,
        timeout: int = 60
    ) -> tuple[int, str, str]:
        """Run a command on a remote host via SSH."""
        ssh_opts = [
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=10",
            "-p", str(port),
        ]
        
        if key_path:
            ssh_opts.extend(["-i", key_path])
            ssh_opts.extend(["-o", "BatchMode=yes"])
        
        ssh_cmd = ["ssh"] + ssh_opts + [f"{username}@{host}", command]
        
        # If using password, use sshpass
        if password and not key_path:
            ssh_cmd = ["sshpass", "-p", password] + ssh_cmd
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode or 0, stdout.decode(), stderr.decode()
        except asyncio.TimeoutError:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)
    
    async def _scp_file(
        self,
        host: str,
        username: str,
        local_path: str,
        remote_path: str,
        password: Optional[str] = None,
        key_path: Optional[str] = None,
        port: int = 22,
        timeout: int = 60
    ) -> tuple[int, str, str]:
        """Copy a file to remote host via SCP."""
        scp_opts = [
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-P", str(port),
        ]
        
        if key_path:
            scp_opts.extend(["-i", key_path])
            scp_opts.extend(["-o", "BatchMode=yes"])
        
        scp_cmd = ["scp"] + scp_opts + [local_path, f"{username}@{host}:{remote_path}"]
        
        if password and not key_path:
            scp_cmd = ["sshpass", "-p", password] + scp_cmd
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *scp_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode or 0, stdout.decode(), stderr.decode()
        except asyncio.TimeoutError:
            return -1, "", "SCP timed out"
        except Exception as e:
            return -1, "", str(e)
    
    async def deploy_agent(
        self,
        client_id: str,
        hostname: str,
        ssh_user: str,
        ssh_password: Optional[str] = None,
        ssh_key_path: Optional[str] = None,
        ssh_port: int = 22,
        agent_port: int = 8080,
        status_callback: Optional[callable] = None,
    ) -> DeploymentResult:
        """Deploy and start agent on a single client."""
        
        async def update_status(status: DeploymentStatus, message: str = ""):
            if status_callback:
                await status_callback(client_id, status, message)
            logger.info(f"[{client_id}] {status.value}: {message}")
        
        await update_status(DeploymentStatus.CONNECTING, f"Connecting to {hostname}")
        
        # Test SSH connection
        rc, stdout, stderr = await self._run_ssh_command(
            hostname, ssh_user, "echo connected",
            ssh_password, ssh_key_path, ssh_port
        )
        
        if rc != 0:
            return DeploymentResult(
                client_id=client_id,
                hostname=hostname,
                status=DeploymentStatus.FAILED,
                message=f"SSH connection failed: {stderr or 'Could not connect'}",
            )
        
        await update_status(DeploymentStatus.INSTALLING, "Setting up Python environment")
        
        # Create agent directory
        remote_dir = "/opt/scale_agent"
        setup_commands = f"""
            mkdir -p {remote_dir}/agent/core {remote_dir}/agent/network {remote_dir}/common/models {remote_dir}/common/messaging
            cd {remote_dir}
            python3 -m venv venv 2>/dev/null || python3.9 -m venv venv 2>/dev/null || python -m venv venv
            source venv/bin/activate
            pip install --upgrade pip -q
            pip install {' '.join(self.AGENT_REQUIREMENTS)} -q
            echo "setup complete"
        """
        
        rc, stdout, stderr = await self._run_ssh_command(
            hostname, ssh_user, setup_commands,
            ssh_password, ssh_key_path, ssh_port, timeout=180
        )
        
        if rc != 0 or "setup complete" not in stdout:
            return DeploymentResult(
                client_id=client_id,
                hostname=hostname,
                status=DeploymentStatus.FAILED,
                message=f"Failed to setup environment: {stderr or stdout}",
            )
        
        await update_status(DeploymentStatus.COPYING, "Copying agent files")
        
        # Copy agent files
        for file_path in self.AGENT_FILES:
            local_file = self.base_path / file_path
            if not local_file.exists():
                logger.warning(f"File not found: {local_file}")
                continue
            
            remote_file = f"{remote_dir}/{file_path}"
            
            # Ensure remote directory exists
            remote_file_dir = str(Path(remote_file).parent)
            await self._run_ssh_command(
                hostname, ssh_user, f"mkdir -p {remote_file_dir}",
                ssh_password, ssh_key_path, ssh_port
            )
            
            rc, stdout, stderr = await self._scp_file(
                hostname, ssh_user, str(local_file), remote_file,
                ssh_password, ssh_key_path, ssh_port
            )
            
            if rc != 0:
                return DeploymentResult(
                    client_id=client_id,
                    hostname=hostname,
                    status=DeploymentStatus.FAILED,
                    message=f"Failed to copy {file_path}: {stderr}",
                )
        
        await update_status(DeploymentStatus.STARTING, "Starting agent service")
        
        # Create agent startup script
        startup_script = f'''#!/bin/bash
cd {remote_dir}
source venv/bin/activate
export AGENT_ID="{client_id}"
export AGENT_PORT="{agent_port}"
export MANAGER_URL="http://{self.manager_host}:{self.manager_port}"
export REDIS_URL="redis://{self.redis_host}:{self.redis_port}"
export PYTHONPATH="{remote_dir}"

# Kill any existing agent
pkill -f "python -m agent.main" 2>/dev/null || true

# Start agent in background
nohup python -m agent.main > /var/log/scale_agent.log 2>&1 &
echo $! > {remote_dir}/agent.pid
echo "Agent started with PID $(cat {remote_dir}/agent.pid)"
'''
        
        # Write and run startup script
        rc, stdout, stderr = await self._run_ssh_command(
            hostname, ssh_user,
            f"cat > {remote_dir}/start_agent.sh << 'SCRIPT'\n{startup_script}\nSCRIPT\nchmod +x {remote_dir}/start_agent.sh && {remote_dir}/start_agent.sh",
            ssh_password, ssh_key_path, ssh_port
        )
        
        if rc != 0:
            return DeploymentResult(
                client_id=client_id,
                hostname=hostname,
                status=DeploymentStatus.FAILED,
                message=f"Failed to start agent: {stderr or stdout}",
            )
        
        # Wait a moment and verify agent is running
        await asyncio.sleep(2)
        
        rc, stdout, stderr = await self._run_ssh_command(
            hostname, ssh_user,
            f"pgrep -f 'python -m agent.main' && curl -s http://localhost:{agent_port}/health || echo 'not running'",
            ssh_password, ssh_key_path, ssh_port
        )
        
        if "not running" in stdout or rc != 0:
            # Check logs for error
            rc, log_output, _ = await self._run_ssh_command(
                hostname, ssh_user, "tail -20 /var/log/scale_agent.log 2>/dev/null",
                ssh_password, ssh_key_path, ssh_port
            )
            return DeploymentResult(
                client_id=client_id,
                hostname=hostname,
                status=DeploymentStatus.FAILED,
                message=f"Agent failed to start. Logs: {log_output[:500]}",
            )
        
        await update_status(DeploymentStatus.SUCCESS, f"Agent running on port {agent_port}")
        
        return DeploymentResult(
            client_id=client_id,
            hostname=hostname,
            status=DeploymentStatus.SUCCESS,
            message=f"Agent deployed and running on port {agent_port}",
            agent_port=agent_port,
        )
    
    async def deploy_to_clients(
        self,
        clients: list[dict],
        status_callback: Optional[callable] = None,
    ) -> list[DeploymentResult]:
        """Deploy agent to multiple clients in parallel."""
        tasks = []
        
        for client in clients:
            task = self.deploy_agent(
                client_id=client.get("id"),
                hostname=client.get("hostname"),
                ssh_user=client.get("ssh_user", "root"),
                ssh_password=client.get("ssh_password"),
                ssh_key_path=client.get("ssh_key_path"),
                ssh_port=client.get("ssh_port", 22),
                agent_port=client.get("agent_port", 8080),
                status_callback=status_callback,
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to failed results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(DeploymentResult(
                    client_id=clients[i].get("id"),
                    hostname=clients[i].get("hostname"),
                    status=DeploymentStatus.FAILED,
                    message=str(result),
                ))
            else:
                final_results.append(result)
        
        return final_results
    
    async def stop_agent(
        self,
        hostname: str,
        ssh_user: str,
        ssh_password: Optional[str] = None,
        ssh_key_path: Optional[str] = None,
        ssh_port: int = 22,
    ) -> bool:
        """Stop the agent on a client."""
        rc, stdout, stderr = await self._run_ssh_command(
            hostname, ssh_user,
            "pkill -f 'python -m agent.main' && rm -f /opt/scale_agent/agent.pid",
            ssh_password, ssh_key_path, ssh_port
        )
        return rc == 0
    
    async def check_agent_status(
        self,
        hostname: str,
        ssh_user: str,
        ssh_password: Optional[str] = None,
        ssh_key_path: Optional[str] = None,
        ssh_port: int = 22,
        agent_port: int = 8080,
    ) -> dict:
        """Check if agent is running on a client."""
        rc, stdout, stderr = await self._run_ssh_command(
            hostname, ssh_user,
            f"curl -s http://localhost:{agent_port}/health 2>/dev/null",
            ssh_password, ssh_key_path, ssh_port, timeout=10
        )
        
        if rc == 0 and stdout.strip():
            try:
                import json
                return json.loads(stdout)
            except:
                return {"status": "unknown", "raw": stdout}
        
        return {"status": "not_running"}
