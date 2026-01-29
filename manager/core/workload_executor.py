"""SSH-based workload executor for running FIO on clients."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class WorkloadExecutor:
    """Execute workloads on clients via SSH."""
    
    def __init__(self):
        self.running_clients: Dict[str, asyncio.subprocess.Process] = {}
        self.command_log: List[Dict[str, Any]] = []  # Store executed commands
    
    def log_command(self, client_id: str, command: str, description: str) -> None:
        """Log a command for tracking/debugging."""
        self.command_log.append({
            "timestamp": datetime.now().isoformat(),
            "client_id": client_id,
            "command": command,
            "description": description,
        })
        logger.info(f"[{client_id}] {description}: {command[:200]}{'...' if len(command) > 200 else ''}")
    
    def get_command_log(self) -> List[Dict[str, Any]]:
        """Get all logged commands."""
        return self.command_log.copy()
    
    def clear_command_log(self) -> None:
        """Clear the command log."""
        self.command_log = []
    
    async def ensure_fio_installed(
        self,
        client: dict,
    ) -> tuple[bool, str]:
        """Check if FIO is installed on client, install if missing."""
        host = client.get("hostname")
        username = client.get("ssh_user", "root")
        password = client.get("ssh_password")
        key_path = client.get("ssh_key_path")
        port = client.get("ssh_port", 22)
        client_id = client.get("id", host)
        
        # Check if FIO is already installed
        check_cmd = "which fio"
        self.log_command(client_id, check_cmd, "Check if FIO is installed")
        
        rc, stdout, stderr = await self.run_ssh_command(
            host, username, check_cmd, password, key_path, port, timeout=30
        )
        
        if rc == 0:
            # FIO is installed, get version
            version_cmd = "fio --version"
            rc, version_out, _ = await self.run_ssh_command(
                host, username, version_cmd, password, key_path, port, timeout=30
            )
            version = version_out.strip() if rc == 0 else "unknown"
            logger.info(f"FIO already installed on {host}: {version}")
            return True, f"FIO already installed: {version}"
        
        # FIO not installed, install it
        logger.info(f"Installing FIO on {host}")
        
        # Try different package managers (with proper grouping for apt-get)
        install_cmd = (
            "yum install -y fio 2>/dev/null || "
            "dnf install -y fio 2>/dev/null || "
            "(apt-get update && apt-get install -y fio) 2>/dev/null || "
            "zypper install -y fio 2>/dev/null || "
            "echo 'No package manager found'"
        )
        
        self.log_command(client_id, install_cmd, "Install FIO")
        
        rc, stdout, stderr = await self.run_ssh_command(
            host, username, install_cmd, password, key_path, port, timeout=300
        )
        
        if rc != 0:
            error_msg = f"Failed to install FIO: {stderr or stdout}"
            self.log_command(client_id, f"# FAILED: {error_msg}", "Install FIO result")
            return False, error_msg
        
        # Verify installation
        rc, version_out, _ = await self.run_ssh_command(
            host, username, "fio --version", password, key_path, port, timeout=30
        )
        
        if rc != 0:
            error_msg = "FIO installation verification failed"
            self.log_command(client_id, f"# FAILED: {error_msg}", "Verify FIO")
            return False, error_msg
        
        version = version_out.strip()
        self.log_command(client_id, f"# SUCCESS: {version}", "FIO installed")
        logger.info(f"FIO installed successfully on {host}: {version}")
        return True, f"FIO installed: {version}"
    
    async def ensure_fio_on_clients(
        self,
        clients: list[dict],
    ) -> list[tuple[str, bool, str]]:
        """Ensure FIO is installed on all clients."""
        tasks = [self.ensure_fio_installed(client) for client in clients]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        output = []
        for i, result in enumerate(results):
            client_id = clients[i].get("id", f"client_{i}")
            if isinstance(result, Exception):
                output.append((client_id, False, str(result)))
            else:
                output.append((client_id, result[0], result[1]))
        
        return output
    
    async def push_ceph_config_to_client(
        self,
        client: dict,
        cluster_config: dict,
    ) -> tuple[bool, str]:
        """
        Copy Ceph config files from cluster installer node to a client.
        Fetches /etc/ceph/ceph.conf and keyring from installer node and pushes to client.
        """
        installer_node = cluster_config.get("installer_node", {})
        ceph_config = cluster_config.get("ceph", {})
        
        if not installer_node or not installer_node.get("host"):
            return False, "No installer node configured for cluster"
        
        installer_host = installer_node.get("host")
        installer_user = installer_node.get("username", "root")
        installer_port = installer_node.get("port", 22)
        
        # Client SSH details
        client_host = client.get("hostname")
        client_user = client.get("ssh_user", "root")
        client_password = client.get("ssh_password")
        client_key_path = client.get("ssh_key_path")
        client_port = client.get("ssh_port", 22)
        
        # We need to get the SSH credentials for the installer from somewhere
        # For now, we'll use the client's SSH credentials to access installer
        # (assuming they have the same credentials, or key-based auth)
        installer_password = client_password
        installer_key_path = client_key_path
        
        conf_path = ceph_config.get("conf_path", "/etc/ceph/ceph.conf")
        keyring_path = ceph_config.get("keyring_path", "/etc/ceph/ceph.client.admin.keyring")
        user = ceph_config.get("user", "admin")
        
        logger.info(f"Pushing Ceph config from {installer_host} to {client_host}")
        
        # Step 1: Fetch ceph.conf from installer node
        rc, conf_content, stderr = await self.run_ssh_command(
            installer_host, installer_user, f"cat {conf_path}",
            installer_password, installer_key_path, installer_port
        )
        
        if rc != 0:
            return False, f"Failed to fetch ceph.conf from installer: {stderr}"
        
        # Step 2: Fetch keyring from installer node
        rc, keyring_content, stderr = await self.run_ssh_command(
            installer_host, installer_user, f"cat {keyring_path}",
            installer_password, installer_key_path, installer_port
        )
        
        if rc != 0:
            # Try alternative keyring path
            alt_keyring = f"/etc/ceph/ceph.client.{user}.keyring"
            rc, keyring_content, stderr = await self.run_ssh_command(
                installer_host, installer_user, f"cat {alt_keyring}",
                installer_password, installer_key_path, installer_port
            )
            if rc != 0:
                return False, f"Failed to fetch keyring from installer: {stderr}"
        
        # Step 3: Create /etc/ceph directory on client
        rc, _, stderr = await self.run_ssh_command(
            client_host, client_user, "mkdir -p /etc/ceph && chmod 755 /etc/ceph",
            client_password, client_key_path, client_port
        )
        
        if rc != 0:
            return False, f"Failed to create /etc/ceph on client: {stderr}"
        
        # Step 4: Write ceph.conf to client
        # Escape single quotes in content
        escaped_conf = conf_content.replace("'", "'\\''")
        rc, _, stderr = await self.run_ssh_command(
            client_host, client_user,
            f"cat > /etc/ceph/ceph.conf << 'CEPHCONF'\n{conf_content}\nCEPHCONF",
            client_password, client_key_path, client_port
        )
        
        if rc != 0:
            return False, f"Failed to write ceph.conf to client: {stderr}"
        
        # Step 5: Write keyring to client
        keyring_filename = f"/etc/ceph/ceph.client.{user}.keyring"
        rc, _, stderr = await self.run_ssh_command(
            client_host, client_user,
            f"cat > {keyring_filename} << 'KEYRING'\n{keyring_content}\nKEYRING\nchmod 600 {keyring_filename}",
            client_password, client_key_path, client_port
        )
        
        if rc != 0:
            return False, f"Failed to write keyring to client: {stderr}"
        
        logger.info(f"Successfully pushed Ceph config to {client_host}")
        return True, f"Ceph config pushed to {client_host}"
    
    async def push_ceph_config_to_clients(
        self,
        clients: list[dict],
        cluster_config: dict,
    ) -> list[tuple[str, bool, str]]:
        """Push Ceph config to multiple clients in parallel."""
        tasks = [
            self.push_ceph_config_to_client(client, cluster_config)
            for client in clients
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        output = []
        for i, result in enumerate(results):
            client_id = clients[i].get("id", f"client_{i}")
            if isinstance(result, Exception):
                output.append((client_id, False, str(result)))
            else:
                output.append((client_id, result[0], result[1]))
        
        return output
    
    async def run_ssh_command(
        self,
        host: str,
        username: str,
        command: str,
        password: Optional[str] = None,
        key_path: Optional[str] = None,
        port: int = 22,
        timeout: int = 300
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
    
    async def install_ceph_common(
        self,
        client: dict,
        repo_url: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Install ceph-common on a client."""
        host = client.get("hostname")
        username = client.get("ssh_user", "root")
        password = client.get("ssh_password")
        key_path = client.get("ssh_key_path")
        port = client.get("ssh_port", 22)
        
        commands = []
        
        # Add repo if provided
        if repo_url:
            repo_content = f"""[ceph]
name=Ceph packages
baseurl={repo_url}
enabled=1
gpgcheck=0
"""
            # Create repo file
            commands.append(f"cat > /etc/yum.repos.d/ceph.repo << 'EOF'\n{repo_content}\nEOF")
        
        # Install ceph-common (with proper grouping for apt-get)
        commands.append(
            "yum install -y ceph-common 2>/dev/null || "
            "dnf install -y ceph-common 2>/dev/null || "
            "(apt-get update && apt-get install -y ceph-common) 2>/dev/null || "
            "zypper install -y ceph-common 2>/dev/null"
        )
        
        full_command = " && ".join(commands)
        
        # Log the command
        client_id = client.get("id", host)
        self.log_command(client_id, full_command, "Install ceph-common")
        
        logger.info(f"Installing ceph-common on {host}")
        rc, stdout, stderr = await self.run_ssh_command(
            host, username, full_command, password, key_path, port, timeout=300
        )
        
        if rc != 0:
            error_msg = f"Failed to install ceph-common: {stderr or stdout}"
            self.log_command(client_id, f"# FAILED: {error_msg}", "Install result")
            return False, error_msg
        
        self.log_command(client_id, "# SUCCESS", "Install result")
        return True, "ceph-common installed successfully"
    
    async def mount_filesystem(
        self,
        client: dict,
        mount_config: dict,
        cluster_config: dict,
    ) -> tuple[bool, str]:
        """Mount a filesystem on a client."""
        host = client.get("hostname")
        username = client.get("ssh_user", "root")
        password = client.get("ssh_password")
        key_path = client.get("ssh_key_path")
        port = client.get("ssh_port", 22)
        
        fs_type = mount_config.get("filesystem_type", "cephfs")
        mount_point = mount_config.get("mount_point", "/mnt/scale_test")
        mount_options = mount_config.get("mount_options", "")
        
        # Create mount point
        await self.run_ssh_command(
            host, username, f"mkdir -p {mount_point}",
            password, key_path, port
        )
        
        # Unmount if already mounted
        await self.run_ssh_command(
            host, username, f"umount {mount_point} 2>/dev/null || true",
            password, key_path, port
        )
        
        # Build mount command based on filesystem type
        if fs_type == "cephfs":
            mount_cmd = self._build_cephfs_mount(mount_config, cluster_config, mount_point, mount_options)
        elif fs_type == "nfs":
            mount_cmd = self._build_nfs_mount(mount_config, mount_point, mount_options)
        elif fs_type == "glusterfs":
            mount_cmd = self._build_gluster_mount(mount_config, mount_point, mount_options)
        else:
            return False, f"Unsupported filesystem type: {fs_type}"
        
        # Log the mount command
        client_id = client.get("id", host)
        self.log_command(client_id, mount_cmd, f"Mount {fs_type} filesystem")
        
        logger.info(f"Mounting {fs_type} on {host}:{mount_point}")
        rc, stdout, stderr = await self.run_ssh_command(
            host, username, mount_cmd, password, key_path, port, timeout=60
        )
        
        if rc != 0:
            error_msg = f"Mount failed: {stderr or stdout}"
            self.log_command(client_id, f"# FAILED: {error_msg}", "Mount result")
            return False, error_msg
        
        # Verify mount
        verify_cmd = f"mountpoint -q {mount_point}"
        self.log_command(client_id, verify_cmd, "Verify mount point")
        rc, stdout, stderr = await self.run_ssh_command(
            host, username, verify_cmd,
            password, key_path, port
        )
        
        if rc != 0:
            return False, f"Mount point verification failed"
        
        return True, f"Successfully mounted {fs_type} at {mount_point}"
    
    def _build_cephfs_mount(
        self,
        mount_config: dict,
        cluster_config: dict,
        mount_point: str,
        extra_options: str,
    ) -> str:
        """
        Build CephFS kernel mount command.
        
        Two mount methods supported:
        1. Kernel mount (default): mount -t ceph ...
        2. FUSE mount: ceph-fuse ...
        
        Kernel mount syntax:
          mount -t ceph <mon1>:<port>,<mon2>:<port>:<path> <mount_point> -o name=<user>,secret=<key>
        
        Note: Newer kernels don't support 'secretfile=' option directly.
        We extract the secret from keyring and pass it with 'secret=' option.
        
        Reference: https://docs.ceph.com/en/latest/cephfs/mount-using-kernel-driver/
        """
        ceph_config = cluster_config.get("ceph", {})
        monitors = ceph_config.get("monitors", [])
        user = mount_config.get("cephfs_user", ceph_config.get("user", "admin"))
        cephfs_path = mount_config.get("cephfs_path", "/")
        secret_file = mount_config.get("cephfs_secret_file")
        mount_method = mount_config.get("mount_method", "kernel")  # 'kernel' or 'fuse'
        
        if not monitors:
            monitors = ["localhost:6789"]
        
        # Ensure monitors have port
        formatted_monitors = []
        for mon in monitors:
            if ":" not in mon:
                formatted_monitors.append(f"{mon}:6789")
            else:
                formatted_monitors.append(mon)
        
        # Default keyring path
        if not secret_file:
            secret_file = f"/etc/ceph/ceph.client.{user}.keyring"
        
        if mount_method == "fuse":
            # FUSE mount: ceph-fuse --id <user> -m <mon1>:6789,<mon2>:6789 <mount_point>
            mon_str = ",".join(formatted_monitors)
            cmd = f"ceph-fuse --id {user} -k {secret_file} -m {mon_str}"
            if cephfs_path and cephfs_path != "/":
                cmd += f" -r {cephfs_path}"
            cmd += f" {mount_point}"
            return cmd
        else:
            # Kernel mount (default)
            # Format: mount -t ceph mon1:port,mon2:port:/<path> <mount_point> -o name=<user>,secret=<key>
            # 
            # Note: Newer kernels don't support 'secretfile=' option.
            # We extract the secret from the keyring and pass it with 'secret=' option.
            mon_str = ",".join(formatted_monitors)
            device_str = f"{mon_str}:{cephfs_path}"
            
            # Build mount command with inline secret extraction
            # The keyring file format is:
            # [client.admin]
            #     key = AQBxxxxxxxxxxxxxxx==
            # 
            # Extract secret and mount in one command
            extra_opts = f",{extra_options}" if extra_options else ""
            
            # Simple approach: use ceph-authtool if available, otherwise grep
            cmd = (
                f"SECRET=$(ceph-authtool {secret_file} -n client.{user} -p 2>/dev/null || "
                f"grep -A1 'client.{user}' {secret_file} | grep key | awk '{{{{print $3}}}}') && "
                f"mount -t ceph {device_str} {mount_point} -o name={user},secret=$SECRET{extra_opts}"
            )
            
            return cmd
    
    def _build_nfs_mount(
        self,
        mount_config: dict,
        mount_point: str,
        extra_options: str,
    ) -> str:
        """Build NFS mount command."""
        server = mount_config.get("nfs_server")
        export = mount_config.get("nfs_export")
        version = mount_config.get("nfs_version", "4.1")
        
        options = [f"vers={version}"]
        if extra_options:
            options.append(extra_options)
        
        opts_str = ",".join(options)
        
        return f"mount -t nfs -o {opts_str} {server}:{export} {mount_point}"
    
    def _build_gluster_mount(
        self,
        mount_config: dict,
        mount_point: str,
        extra_options: str,
    ) -> str:
        """Build GlusterFS mount command."""
        servers = mount_config.get("gluster_servers", [])
        volume = mount_config.get("gluster_volume")
        
        if not servers:
            return "echo 'No GlusterFS servers specified' && exit 1"
        
        server = servers[0]  # Use first server
        
        options = ["backup-volfile-servers=" + ",".join(servers[1:])] if len(servers) > 1 else []
        if extra_options:
            options.append(extra_options)
        
        if options:
            opts_str = " -o " + ",".join(options)
        else:
            opts_str = ""
        
        return f"mount -t glusterfs{opts_str} {server}:/{volume} {mount_point}"
    
    async def unmount_filesystem(
        self,
        client: dict,
        mount_point: str,
    ) -> tuple[bool, str]:
        """Unmount a filesystem from a client."""
        host = client.get("hostname")
        username = client.get("ssh_user", "root")
        password = client.get("ssh_password")
        key_path = client.get("ssh_key_path")
        port = client.get("ssh_port", 22)
        
        logger.info(f"Unmounting {mount_point} on {host}")
        
        # Force unmount
        rc, stdout, stderr = await self.run_ssh_command(
            host, username, f"umount -f {mount_point} 2>/dev/null; rm -rf {mount_point}/fio_test_*",
            password, key_path, port
        )
        
        return True, "Unmounted"
    
    async def run_fio(
        self,
        client: dict,
        workload_config: dict,
        execution_id: str,
    ) -> tuple[bool, str, dict]:
        """Run FIO on a client and return results."""
        host = client.get("hostname")
        username = client.get("ssh_user", "root")
        password = client.get("ssh_password")
        key_path = client.get("ssh_key_path")
        port = client.get("ssh_port", 22)
        
        io_config = workload_config.get("io", {})
        test_config = workload_config.get("test", {})
        mount_config = workload_config.get("mount", {})
        
        # Determine test directory
        if mount_config:
            directory = mount_config.get("mount_point", "/mnt/scale_test")
        else:
            directory = "/tmp/fio_test"
        
        # Build FIO command
        fio_cmd = self._build_fio_command(
            io_config=io_config,
            test_config=test_config,
            directory=directory,
            execution_id=execution_id,
            client_id=client.get("id"),
        )
        
        # Log the FIO command
        client_id = client.get("id", host)
        self.log_command(client_id, fio_cmd, "Run FIO benchmark")
        
        logger.info(f"Running FIO on {host}: {fio_cmd[:100]}...")
        
        # Run FIO with JSON output
        rc, stdout, stderr = await self.run_ssh_command(
            host, username, fio_cmd, password, key_path, port,
            timeout=test_config.get("duration", 60) + 120  # Extra time for ramp and cleanup
        )
        
        if rc != 0:
            error_msg = f"FIO failed: {stderr or stdout}"
            self.log_command(client_id, f"# FAILED: {error_msg}", "FIO result")
            return False, error_msg, {}
        
        # Parse FIO JSON output
        try:
            # Find JSON in output (FIO outputs text then JSON)
            json_start = stdout.find('{')
            if json_start >= 0:
                fio_result = json.loads(stdout[json_start:])
                metrics = self._parse_fio_results(fio_result)
                return True, "FIO completed", metrics
            else:
                return True, "FIO completed (no JSON output)", {}
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse FIO JSON: {e}")
            return True, "FIO completed (invalid JSON)", {}
    
    def _build_fio_command(
        self,
        io_config: dict,
        test_config: dict,
        directory: str,
        execution_id: str,
        client_id: str,
    ) -> str:
        """Build FIO command line."""
        pattern = io_config.get("pattern", "random")
        block_size = io_config.get("block_size", "4k")
        read_pct = io_config.get("read_percent", 100)
        io_depth = io_config.get("io_depth", 32)
        num_jobs = io_config.get("num_jobs", 1)
        direct_io = io_config.get("direct_io", True)
        
        duration = test_config.get("duration", 60)
        ramp_time = test_config.get("ramp_time", 0)
        file_size = test_config.get("file_size", "1G")
        
        # Determine FIO rw mode
        if read_pct == 100:
            rw = "randread" if pattern == "random" else "read"
        elif read_pct == 0:
            rw = "randwrite" if pattern == "random" else "write"
        else:
            rw = "randrw" if pattern == "random" else "rw"
        
        # Build command
        fio_args = [
            "fio",
            f"--name=scale_test_{client_id}",
            f"--directory={directory}",
            f"--rw={rw}",
            f"--bs={block_size}",
            f"--size={file_size}",
            f"--numjobs={num_jobs}",
            f"--iodepth={io_depth}",
            f"--runtime={duration}",
            "--time_based",
            "--group_reporting",
            "--output-format=json",
        ]
        
        if rw in ["randrw", "rw"]:
            fio_args.append(f"--rwmixread={read_pct}")
        
        if direct_io:
            fio_args.append("--direct=1")
        
        if ramp_time > 0:
            fio_args.append(f"--ramp_time={ramp_time}")
        
        # Use libaio on Linux
        fio_args.extend(["--ioengine=libaio", "--end_fsync=1"])
        
        return " ".join(fio_args)
    
    def _parse_fio_results(self, fio_result: dict) -> dict:
        """Parse FIO JSON output and extract metrics."""
        jobs = fio_result.get("jobs", [])
        if not jobs:
            return {}
        
        # Aggregate all jobs
        total_read_iops = 0
        total_write_iops = 0
        total_read_bw = 0  # KB/s
        total_write_bw = 0
        total_read_lat = 0
        total_write_lat = 0
        read_count = 0
        write_count = 0
        
        for job in jobs:
            read_stats = job.get("read", {})
            write_stats = job.get("write", {})
            
            if read_stats.get("iops", 0) > 0:
                total_read_iops += read_stats.get("iops", 0)
                total_read_bw += read_stats.get("bw", 0)
                total_read_lat += read_stats.get("lat_ns", {}).get("mean", 0)
                read_count += 1
            
            if write_stats.get("iops", 0) > 0:
                total_write_iops += write_stats.get("iops", 0)
                total_write_bw += write_stats.get("bw", 0)
                total_write_lat += write_stats.get("lat_ns", {}).get("mean", 0)
                write_count += 1
        
        # Calculate averages
        avg_read_lat = total_read_lat / read_count / 1000 if read_count > 0 else 0  # ns to us
        avg_write_lat = total_write_lat / write_count / 1000 if write_count > 0 else 0
        
        return {
            "iops": {
                "r": int(total_read_iops),
                "w": int(total_write_iops),
                "t": int(total_read_iops + total_write_iops),
            },
            "bw_mbps": {
                "r": total_read_bw / 1024,  # KB/s to MB/s
                "w": total_write_bw / 1024,
                "t": (total_read_bw + total_write_bw) / 1024,
            },
            "lat_us": {
                "r": avg_read_lat,
                "w": avg_write_lat,
                "avg": (avg_read_lat + avg_write_lat) / 2 if (read_count + write_count) > 0 else 0,
            },
        }
    
    async def run_fill_cluster(
        self,
        client: dict,
        fill_config: dict,
        cluster_config: dict,
        execution_id: str,
    ) -> tuple[bool, str, dict]:
        """
        Run fill cluster workload on a client.
        Writes data until target fill percentage is reached.
        """
        host = client.get("hostname")
        username = client.get("ssh_user", "root")
        password = client.get("ssh_password")
        key_path = client.get("ssh_key_path")
        port = client.get("ssh_port", 22)
        client_id = client.get("id", host)
        
        storage_type = fill_config.get("storage_type", "cephfs")
        target_percent = fill_config.get("target_fill_percent", 50)
        file_size = fill_config.get("file_size", "1G")
        num_parallel = fill_config.get("num_parallel_writes", 4)
        replication_factor = fill_config.get("replication_factor", 3)
        
        logger.info(f"Starting fill cluster on {host}: target={target_percent}%, replication={replication_factor}x")
        
        if storage_type == "cephfs":
            # CephFS fill - write files to mounted filesystem
            fs_name = fill_config.get("filesystem_name", "cephfs")
            cephfs_path = fill_config.get("cephfs_path", "/")
            mount_point = fill_config.get("mount_point", "/mnt/scale_test")
            
            # Create fill directory
            fill_dir = f"{mount_point}/fill_cluster_{execution_id}"
            mkdir_cmd = f"mkdir -p {fill_dir}"
            self.log_command(client_id, mkdir_cmd, "Create fill directory")
            
            rc, _, stderr = await self.run_ssh_command(
                host, username, mkdir_cmd, password, key_path, port
            )
            
            if rc != 0:
                return False, f"Failed to create fill directory: {stderr}", {}
            
            # Use FIO to fill with sequential writes
            fio_cmd = (
                f"fio --name=fill_cluster "
                f"--directory={fill_dir} "
                f"--rw=write "
                f"--bs=1m "
                f"--size={file_size} "
                f"--numjobs={num_parallel} "
                f"--direct=1 "
                f"--ioengine=libaio "
                f"--group_reporting "
                f"--output-format=json "
                f"--time_based=0 "
                f"--end_fsync=1"
            )
            
            self.log_command(client_id, fio_cmd, f"Fill cluster (target: {target_percent}%)")
            
            rc, stdout, stderr = await self.run_ssh_command(
                host, username, fio_cmd, password, key_path, port, timeout=3600
            )
            
            if rc != 0:
                error_msg = f"Fill cluster failed: {stderr or stdout}"
                self.log_command(client_id, f"# FAILED: {error_msg}", "Fill result")
                return False, error_msg, {}
            
            # Parse results
            try:
                json_start = stdout.find('{')
                if json_start >= 0:
                    result = json.loads(stdout[json_start:])
                    metrics = self._parse_fio_results(result)
                    
                    # Calculate data written (accounting for replication)
                    raw_written_bytes = result.get("jobs", [{}])[0].get("write", {}).get("io_bytes", 0)
                    effective_written = raw_written_bytes * replication_factor
                    
                    metrics["raw_written_bytes"] = raw_written_bytes
                    metrics["effective_written_bytes"] = effective_written
                    metrics["replication_factor"] = replication_factor
                    
                    self.log_command(
                        client_id, 
                        f"# SUCCESS: Wrote {raw_written_bytes/(1024**3):.2f} GB raw, "
                        f"{effective_written/(1024**3):.2f} GB effective (with {replication_factor}x replication)",
                        "Fill result"
                    )
                    
                    return True, "Fill completed", metrics
            except Exception as e:
                logger.warning(f"Failed to parse fill results: {e}")
            
            return True, "Fill completed", {}
            
        elif storage_type == "rbd":
            # RBD fill - create and fill RBD images
            pool_name = fill_config.get("pool_name", "rbd")
            image_prefix = fill_config.get("image_prefix", "fill_test")
            
            # Create RBD image
            image_name = f"{image_prefix}_{client_id}_{execution_id}"
            create_cmd = f"rbd create {pool_name}/{image_name} --size {file_size}"
            
            self.log_command(client_id, create_cmd, "Create RBD image")
            
            rc, _, stderr = await self.run_ssh_command(
                host, username, create_cmd, password, key_path, port
            )
            
            if rc != 0:
                return False, f"Failed to create RBD image: {stderr}", {}
            
            # Map RBD device
            map_cmd = f"rbd map {pool_name}/{image_name}"
            self.log_command(client_id, map_cmd, "Map RBD device")
            
            rc, stdout, stderr = await self.run_ssh_command(
                host, username, map_cmd, password, key_path, port
            )
            
            if rc != 0:
                return False, f"Failed to map RBD device: {stderr}", {}
            
            rbd_device = stdout.strip()
            
            # Write data using dd
            dd_cmd = f"dd if=/dev/zero of={rbd_device} bs=1M oflag=direct status=progress 2>&1"
            self.log_command(client_id, dd_cmd, f"Fill RBD device {rbd_device}")
            
            rc, stdout, stderr = await self.run_ssh_command(
                host, username, dd_cmd, password, key_path, port, timeout=3600
            )
            
            # Unmap device
            unmap_cmd = f"rbd unmap {rbd_device}"
            self.log_command(client_id, unmap_cmd, "Unmap RBD device")
            await self.run_ssh_command(host, username, unmap_cmd, password, key_path, port)
            
            return True, "RBD fill completed", {"device": rbd_device, "image": image_name}
            
        elif storage_type == "rgw":
            # RGW fill - upload objects to bucket
            bucket_name = fill_config.get("bucket_name", "fill-test")
            
            # Use s3cmd or aws cli to upload data
            # For now, use dd + radosgw-admin or aws cli
            s3_config = cluster_config.get("s3", {})
            endpoint = s3_config.get("endpoint", "")
            access_key = s3_config.get("access_key", "")
            secret_key = s3_config.get("secret_key", "")
            
            # Generate and upload files
            fill_cmd = (
                f"for i in $(seq 1 {num_parallel}); do "
                f"dd if=/dev/urandom bs=1M count=1024 2>/dev/null | "
                f"aws s3 cp - s3://{bucket_name}/fill_${{i}}_{execution_id} "
                f"--endpoint-url {endpoint} & "
                f"done; wait"
            )
            
            self.log_command(client_id, fill_cmd, f"Fill RGW bucket {bucket_name}")
            
            rc, stdout, stderr = await self.run_ssh_command(
                host, username, fill_cmd, password, key_path, port, timeout=3600
            )
            
            if rc != 0:
                return False, f"RGW fill failed: {stderr}", {}
            
            return True, "RGW fill completed", {}
        
        return False, f"Unsupported storage type: {storage_type}", {}

    async def cleanup_client(
        self,
        client: dict,
        mount_point: Optional[str] = None,
    ) -> None:
        """Clean up test files and unmount on a client."""
        host = client.get("hostname")
        username = client.get("ssh_user", "root")
        password = client.get("ssh_password")
        key_path = client.get("ssh_key_path")
        port = client.get("ssh_port", 22)
        
        # Clean up FIO files
        cleanup_cmd = "rm -rf /tmp/fio_test* 2>/dev/null"
        if mount_point:
            cleanup_cmd += f"; rm -rf {mount_point}/scale_test_* 2>/dev/null"
            cleanup_cmd += f"; umount {mount_point} 2>/dev/null || true"
        
        await self.run_ssh_command(host, username, cleanup_cmd, password, key_path, port)
