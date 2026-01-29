"""Cluster management endpoints."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Optional
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

from common.models.cluster import ClusterConfig, StorageType, StorageBackend, CephConnection
from manager.dependencies import get_data_store

router = APIRouter()


class SSHDiscoveryRequest(BaseModel):
    """Request to discover cluster via SSH."""
    host: str
    username: str = "root"
    password: Optional[str] = None
    key_path: Optional[str] = None
    port: int = 22


async def run_ssh_command(
    host: str,
    username: str,
    command: str,
    password: Optional[str] = None,
    key_path: Optional[str] = None,
    port: int = 22,
    timeout: int = 60
) -> tuple[int, str, str]:
    """Run a command on a remote host via SSH."""
    import shutil
    import logging
    logger = logging.getLogger(__name__)
    
    ssh_opts = [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=30",
        "-o", "ServerAliveInterval=10",
        "-o", "LogLevel=ERROR",
        "-p", str(port),
    ]
    
    if key_path:
        ssh_opts.extend(["-i", key_path])
        ssh_opts.extend(["-o", "BatchMode=yes"])
    
    ssh_cmd = ["ssh"] + ssh_opts + [f"{username}@{host}", command]
    
    # If using password, use sshpass
    if password and not key_path:
        if shutil.which("sshpass"):
            ssh_cmd = ["sshpass", "-p", password] + ssh_cmd
        else:
            logger.warning("sshpass not installed, password auth may fail")
    
    logger.debug(f"Running SSH command to {host}: {command[:50]}...")
    
    try:
        proc = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, stdout.decode(errors='replace'), stderr.decode(errors='replace')
    except asyncio.TimeoutError:
        return -1, "", f"Command timed out after {timeout}s"
    except FileNotFoundError as e:
        return -1, "", f"Required command not found: {e}. Ensure sshpass is installed."
    except Exception as e:
        return -1, "", str(e)


@router.post("/discover/")
async def discover_cluster(request: SSHDiscoveryRequest):
    """
    Discover Ceph cluster configuration by SSHing to installer node.
    Returns cluster details including monitors, pools, health, etc.
    """
    host = request.host
    username = request.username
    password = request.password
    key_path = request.key_path
    port = request.port
    
    if not password and not key_path:
        raise HTTPException(status_code=400, detail="Either password or key_path must be provided")
    
    result = {
        "host": host,
        "fsid": None,
        "version": None,
        "health": None,
        "monitors": [],
        "pools": [],
        "user": "admin",
        "keyring_path": "/etc/ceph/ceph.client.admin.keyring",
        "conf_path": "/etc/ceph/ceph.conf",
    }
    
    # Test SSH connectivity first
    rc, stdout, stderr = await run_ssh_command(host, username, "echo ok", password, key_path, port)
    if rc != 0:
        raise HTTPException(
            status_code=400, 
            detail=f"SSH connection failed: {stderr or 'Could not connect to host'}"
        )
    
    # Get cluster health and FSID
    rc, stdout, stderr = await run_ssh_command(
        host, username, "ceph health -f json 2>/dev/null || ceph -s -f json 2>/dev/null",
        password, key_path, port
    )
    if rc == 0 and stdout.strip():
        try:
            health_data = json.loads(stdout)
            result["health"] = health_data.get("status") or health_data.get("health", {}).get("status")
        except json.JSONDecodeError:
            pass
    
    # Get FSID
    rc, stdout, stderr = await run_ssh_command(
        host, username, "ceph fsid 2>/dev/null",
        password, key_path, port
    )
    if rc == 0 and stdout.strip():
        result["fsid"] = stdout.strip()
    
    # Get Ceph version
    rc, stdout, stderr = await run_ssh_command(
        host, username, "ceph version 2>/dev/null | head -1",
        password, key_path, port
    )
    if rc == 0 and stdout.strip():
        # Extract version like "quincy", "reef", etc.
        version_match = re.search(r'ceph version [\d.]+ \(.*\) (\w+)', stdout)
        if version_match:
            result["version"] = version_match.group(1)
        else:
            result["version"] = stdout.strip()[:50]
    
    # Get monitor addresses
    rc, stdout, stderr = await run_ssh_command(
        host, username, "ceph mon dump -f json 2>/dev/null",
        password, key_path, port
    )
    if rc == 0 and stdout.strip():
        try:
            mon_data = json.loads(stdout)
            monitors = []
            for mon in mon_data.get("mons", []):
                # Try to get the addr field
                addr = mon.get("public_addr") or mon.get("addr", "")
                # Clean up address format (remove /0 suffix if present)
                addr = re.sub(r'/\d+$', '', addr)
                if addr:
                    monitors.append(addr)
            result["monitors"] = monitors
        except json.JSONDecodeError:
            pass
    
    # Fallback: get monitors from ceph.conf
    if not result["monitors"]:
        rc, stdout, stderr = await run_ssh_command(
            host, username, "grep -E '^\\s*mon_host' /etc/ceph/ceph.conf 2>/dev/null | head -1",
            password, key_path, port
        )
        if rc == 0 and stdout.strip():
            # Parse mon_host = 192.168.1.10,192.168.1.11
            match = re.search(r'mon_host\s*=\s*(.+)', stdout)
            if match:
                mons = match.group(1).strip()
                result["monitors"] = [m.strip() for m in mons.replace(',', ' ').split() if m.strip()]
    
    # Get pools
    rc, stdout, stderr = await run_ssh_command(
        host, username, "ceph osd pool ls 2>/dev/null",
        password, key_path, port
    )
    if rc == 0 and stdout.strip():
        result["pools"] = [p.strip() for p in stdout.strip().split('\n') if p.strip()]
    
    # Check if ceph.conf exists
    rc, stdout, stderr = await run_ssh_command(
        host, username, "test -f /etc/ceph/ceph.conf && echo exists",
        password, key_path, port
    )
    if rc == 0 and "exists" in stdout:
        result["conf_path"] = "/etc/ceph/ceph.conf"
    
    # Check for keyring
    for keyring_path in [
        "/etc/ceph/ceph.client.admin.keyring",
        "/etc/ceph/ceph.keyring",
        "/etc/ceph/keyring",
    ]:
        rc, stdout, stderr = await run_ssh_command(
            host, username, f"test -f {keyring_path} && echo exists",
            password, key_path, port
        )
        if rc == 0 and "exists" in stdout:
            result["keyring_path"] = keyring_path
            break
    
    # Validate we got essential info
    if not result["monitors"]:
        raise HTTPException(
            status_code=400,
            detail="Could not discover Ceph monitors. Make sure Ceph is installed and configured on the target host."
        )
    
    return result


@router.get("/")
async def list_clusters():
    """List all registered clusters."""
    store = get_data_store()
    clusters = store.get_clusters()
    return {
        "clusters": [c.model_dump(exclude_none=True) for c in clusters],
        "total": len(clusters),
    }


@router.post("/")
async def create_cluster(cluster: ClusterConfig):
    """Register a new cluster."""
    store = get_data_store()
    
    # Check if cluster already exists
    existing = store.get_cluster(cluster.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Cluster '{cluster.name}' already exists")
    
    path = store.save_cluster(cluster)
    return {
        "message": "Cluster registered successfully",
        "name": cluster.name,
        "path": path,
    }


@router.get("/{name}")
async def get_cluster(name: str):
    """Get cluster details by name."""
    store = get_data_store()
    cluster = store.get_cluster(name)
    
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster '{name}' not found")
    
    return cluster.model_dump(exclude_none=True)


@router.put("/{name}")
async def update_cluster(name: str, cluster: ClusterConfig):
    """Update a cluster configuration."""
    store = get_data_store()
    
    existing = store.get_cluster(name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Cluster '{name}' not found")
    
    # If name changed, delete old and create new
    if cluster.name != name:
        store.delete_cluster(name)
    
    path = store.save_cluster(cluster)
    return {
        "message": "Cluster updated successfully",
        "name": cluster.name,
        "path": path,
    }


@router.delete("/{name}")
async def delete_cluster(name: str):
    """Delete a cluster configuration."""
    store = get_data_store()
    
    if not store.delete_cluster(name):
        raise HTTPException(status_code=404, detail=f"Cluster '{name}' not found")
    
    return {"message": f"Cluster '{name}' deleted successfully"}


@router.get("/{name}/health")
async def get_cluster_health(name: str):
    """Get cluster health status."""
    store = get_data_store()
    cluster = store.get_cluster(name)
    
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster '{name}' not found")
    
    # Import here to avoid circular imports
    from manager.prechecks.cluster.ceph import CephHealthChecker
    
    if cluster.backend in [StorageBackend.CEPH_RBD, StorageBackend.CEPHFS]:
        checker = CephHealthChecker(cluster.ceph, installer_node=cluster.installer_node)
        try:
            state = await checker.get_cluster_state()
            checks = await checker.run_all_checks()
            return {
                "cluster": name,
                "health": state.health_status.value if state else "UNKNOWN",
                "checks": [c.model_dump() for c in checks],
                "state": state.model_dump() if state else None,
            }
        except Exception as e:
            return {
                "cluster": name,
                "health": "ERROR",
                "error": str(e),
            }
    
    return {
        "cluster": name,
        "health": "UNKNOWN",
        "message": f"Health check not implemented for {cluster.backend}",
    }


@router.post("/{name}/command")
async def run_cluster_command(
    name: str,
    command: str = Body(..., embed=True),
    timeout: int = Body(default=60, embed=True)
):
    """Run a command on the cluster (e.g., Ceph CLI)."""
    store = get_data_store()
    cluster = store.get_cluster(name)
    
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster '{name}' not found")
    
    from manager.prechecks.cluster.custom_commands import CustomCommandRunner, CustomCommandConfig
    
    runner = CustomCommandRunner(
        ceph_conf=cluster.ceph.conf_path if cluster.ceph else "/etc/ceph/ceph.conf"
    )
    
    config = CustomCommandConfig(
        command=command,
        description="Manual command",
        timeout=timeout,
    )
    
    result = await runner.run_command(config)
    
    return {
        "command": command,
        "success": result.success,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_ms": result.duration_ms,
    }


@router.get("/{name}/filesystems")
async def get_cluster_filesystems(name: str):
    """Get list of CephFS filesystems in the cluster."""
    store = get_data_store()
    cluster = store.get_cluster(name)
    
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster '{name}' not found")
    
    if not cluster.installer_node:
        raise HTTPException(status_code=400, detail="Cluster has no installer node configured")
    
    # Get filesystems via SSH
    host = cluster.installer_node.host
    username = cluster.installer_node.username
    password = cluster.installer_node.password
    key_path = cluster.installer_node.key_path
    port = cluster.installer_node.port
    
    rc, stdout, stderr = await run_ssh_command(
        host, username, "ceph fs ls -f json", 
        password=password, key_path=key_path, port=port
    )
    
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed to get filesystems: {stderr}")
    
    try:
        filesystems = json.loads(stdout)
    except json.JSONDecodeError:
        filesystems = []
    
    return {
        "cluster": name,
        "filesystems": filesystems,
        "total": len(filesystems),
    }


@router.get("/{name}/pools")
async def get_cluster_pools(name: str):
    """Get list of pools with their details (size, replication, usage)."""
    store = get_data_store()
    cluster = store.get_cluster(name)
    
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster '{name}' not found")
    
    if not cluster.installer_node:
        raise HTTPException(status_code=400, detail="Cluster has no installer node configured")
    
    host = cluster.installer_node.host
    username = cluster.installer_node.username
    password = cluster.installer_node.password
    key_path = cluster.installer_node.key_path
    port = cluster.installer_node.port
    
    # Get pool list with details
    rc, stdout, stderr = await run_ssh_command(
        host, username, "ceph osd pool ls detail -f json",
        password=password, key_path=key_path, port=port
    )
    
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed to get pools: {stderr}")
    
    try:
        pools_detail = json.loads(stdout)
    except json.JSONDecodeError:
        pools_detail = []
    
    # Get pool stats (usage)
    rc, stdout, stderr = await run_ssh_command(
        host, username, "ceph df -f json",
        password=password, key_path=key_path, port=port
    )
    
    pool_stats = {}
    if rc == 0:
        try:
            df_data = json.loads(stdout)
            for pool in df_data.get("pools", []):
                pool_stats[pool.get("name")] = {
                    "stored": pool.get("stats", {}).get("stored", 0),
                    "objects": pool.get("stats", {}).get("objects", 0),
                    "used": pool.get("stats", {}).get("bytes_used", 0),
                    "percent_used": pool.get("stats", {}).get("percent_used", 0),
                    "max_avail": pool.get("stats", {}).get("max_avail", 0),
                }
        except json.JSONDecodeError:
            pass
    
    # Combine pool details with stats
    pools = []
    for pool in pools_detail:
        pool_name = pool.get("pool_name", "")
        pool_info = {
            "name": pool_name,
            "id": pool.get("pool_id"),
            "size": pool.get("size", 3),  # Replication factor
            "min_size": pool.get("min_size", 2),
            "pg_num": pool.get("pg_num"),
            "type": pool.get("type", "replicated"),
            "crush_rule": pool.get("crush_rule"),
        }
        
        # Add stats if available
        if pool_name in pool_stats:
            pool_info["stats"] = pool_stats[pool_name]
        
        pools.append(pool_info)
    
    return {
        "cluster": name,
        "pools": pools,
        "total": len(pools),
    }


@router.get("/{name}/capacity")
async def get_cluster_capacity(name: str):
    """Get cluster capacity and usage information."""
    store = get_data_store()
    cluster = store.get_cluster(name)
    
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster '{name}' not found")
    
    if not cluster.installer_node:
        raise HTTPException(status_code=400, detail="Cluster has no installer node configured")
    
    host = cluster.installer_node.host
    username = cluster.installer_node.username
    password = cluster.installer_node.password
    key_path = cluster.installer_node.key_path
    port = cluster.installer_node.port
    
    # Get cluster df
    rc, stdout, stderr = await run_ssh_command(
        host, username, "ceph df -f json",
        password=password, key_path=key_path, port=port
    )
    
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed to get cluster capacity: {stderr}")
    
    try:
        df_data = json.loads(stdout)
        stats = df_data.get("stats", {})
        
        total_bytes = stats.get("total_bytes", 0)
        used_bytes = stats.get("total_used_bytes", 0)
        avail_bytes = stats.get("total_avail_bytes", 0)
        
        return {
            "cluster": name,
            "total_bytes": total_bytes,
            "total_gb": round(total_bytes / (1024**3), 2),
            "total_tb": round(total_bytes / (1024**4), 2),
            "used_bytes": used_bytes,
            "used_gb": round(used_bytes / (1024**3), 2),
            "used_percent": round((used_bytes / total_bytes * 100), 2) if total_bytes > 0 else 0,
            "avail_bytes": avail_bytes,
            "avail_gb": round(avail_bytes / (1024**3), 2),
            "pools": df_data.get("pools", []),
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to parse cluster capacity data")


@router.get("/{name}/pool/{pool_name}/replication")
async def get_pool_replication(name: str, pool_name: str):
    """Get replication factor for a specific pool."""
    store = get_data_store()
    cluster = store.get_cluster(name)
    
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster '{name}' not found")
    
    if not cluster.installer_node:
        raise HTTPException(status_code=400, detail="Cluster has no installer node configured")
    
    host = cluster.installer_node.host
    username = cluster.installer_node.username
    password = cluster.installer_node.password
    key_path = cluster.installer_node.key_path
    port = cluster.installer_node.port
    
    # Get pool size (replication factor)
    rc, stdout, stderr = await run_ssh_command(
        host, username, f"ceph osd pool get {pool_name} size -f json",
        password=password, key_path=key_path, port=port
    )
    
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed to get pool replication: {stderr}")
    
    try:
        size_data = json.loads(stdout)
        replication_factor = size_data.get("size", 3)
    except json.JSONDecodeError:
        replication_factor = 3
    
    return {
        "cluster": name,
        "pool": pool_name,
        "replication_factor": replication_factor,
    }


class RunCommandRequest(BaseModel):
    """Request to run a command on the cluster."""
    command: str
    timeout: int = 60


@router.post("/{name}/run-command")
async def run_cluster_command(name: str, request: RunCommandRequest):
    """Run a CLI command on the cluster's installer node."""
    store = get_data_store()
    cluster = store.get_cluster(name)
    
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster '{name}' not found")
    
    if not cluster.installer_node:
        raise HTTPException(status_code=400, detail="Cluster has no installer node configured")
    
    host = cluster.installer_node.host
    username = cluster.installer_node.username
    password = cluster.installer_node.password
    key_path = cluster.installer_node.key_path
    port = cluster.installer_node.port
    
    # Sanitize command - prevent some dangerous operations
    dangerous_patterns = [
        r'rm\s+-rf\s+/',
        r'mkfs\.',
        r'dd\s+.*of=/dev/',
        r'>\s*/dev/sd',
        r'shutdown',
        r'reboot',
        r'init\s+0',
        r'poweroff',
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, request.command, re.IGNORECASE):
            raise HTTPException(
                status_code=400, 
                detail=f"Command contains potentially dangerous pattern and was blocked"
            )
    
    rc, stdout, stderr = await run_ssh_command(
        host, username, request.command,
        password=password, key_path=key_path, port=port,
        timeout=request.timeout
    )
    
    return {
        "cluster": name,
        "command": request.command,
        "exit_code": rc,
        "stdout": stdout,
        "stderr": stderr,
        "success": rc == 0,
    }
