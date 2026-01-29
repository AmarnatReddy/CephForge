"""SSH client for remote command execution."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SSHCommandResult:
    """Result of an SSH command execution."""
    exit_code: int
    stdout: str
    stderr: str
    
    @property
    def success(self) -> bool:
        return self.exit_code == 0


class SSHClient:
    """Async SSH client using subprocess."""
    
    def __init__(
        self,
        hostname: str,
        username: str = "root",
        private_key_path: Optional[str] = None,
        password: Optional[str] = None,
        port: int = 22,
    ):
        self.hostname = hostname
        self.username = username
        self.private_key_path = private_key_path
        self.password = password
        self.port = port
        self._connected = False
    
    async def connect(self) -> None:
        """Test SSH connection."""
        # Test connection with a simple command
        result = await self.run_command("echo connected", timeout=10, raise_on_error=False)
        if result.success:
            self._connected = True
            logger.debug(f"SSH connected to {self.hostname}")
        else:
            raise ConnectionError(f"Failed to connect to {self.hostname}: {result.stderr}")
    
    async def close(self) -> None:
        """Close the connection (no-op for subprocess-based client)."""
        self._connected = False
    
    def _build_ssh_command(self, command: str) -> list[str]:
        """Build SSH command with proper options."""
        ssh_opts = [
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            "-o", "ConnectTimeout=10",
            "-p", str(self.port),
        ]
        
        if self.private_key_path and os.path.exists(self.private_key_path):
            ssh_opts.extend(["-i", self.private_key_path])
        
        if self.password:
            # Use sshpass for password authentication
            return [
                "sshpass", "-p", self.password,
                "ssh", *ssh_opts,
                f"{self.username}@{self.hostname}",
                command
            ]
        else:
            return [
                "ssh", *ssh_opts,
                f"{self.username}@{self.hostname}",
                command
            ]
    
    async def run_command(
        self,
        command: str,
        timeout: int = 60,
        raise_on_error: bool = True,
    ) -> SSHCommandResult:
        """Execute a command on the remote host."""
        ssh_cmd = self._build_ssh_command(command)
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            
            result = SSHCommandResult(
                exit_code=proc.returncode or 0,
                stdout=stdout.decode(errors='replace'),
                stderr=stderr.decode(errors='replace'),
            )
            
            if raise_on_error and not result.success:
                raise RuntimeError(f"Command failed: {result.stderr or result.stdout}")
            
            return result
            
        except asyncio.TimeoutError:
            return SSHCommandResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
            )
        except FileNotFoundError:
            # sshpass not installed, try without password
            if self.password and "sshpass" in ssh_cmd:
                logger.warning("sshpass not installed, trying without password auth")
                # Remove sshpass from command
                ssh_cmd = ssh_cmd[3:]  # Remove sshpass, -p, password
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *ssh_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                    return SSHCommandResult(
                        exit_code=proc.returncode or 0,
                        stdout=stdout.decode(errors='replace'),
                        stderr=stderr.decode(errors='replace'),
                    )
                except Exception as e:
                    return SSHCommandResult(
                        exit_code=-1,
                        stdout="",
                        stderr=str(e),
                    )
            return SSHCommandResult(
                exit_code=-1,
                stdout="",
                stderr="SSH command failed: sshpass not found for password auth",
            )
        except Exception as e:
            return SSHCommandResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
            )
    
    async def put_text(self, content: str, remote_path: str) -> SSHCommandResult:
        """Write text content to a remote file."""
        # Escape content for shell
        escaped_content = content.replace("'", "'\"'\"'")
        command = f"cat > {remote_path} << 'SCALE_EOF'\n{content}\nSCALE_EOF"
        return await self.run_command(command, timeout=30, raise_on_error=False)
    
    async def get_text(self, remote_path: str) -> str:
        """Read text content from a remote file."""
        result = await self.run_command(f"cat {remote_path}", timeout=30, raise_on_error=False)
        return result.stdout if result.success else ""
