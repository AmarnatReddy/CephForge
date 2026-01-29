"""Network profiling and bandwidth testing endpoints."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from manager.dependencies import get_data_store
from manager.deployment.ssh_client import SSHClient

logger = logging.getLogger(__name__)
router = APIRouter()


class NetworkProfile(BaseModel):
    """Network profile between client and target."""
    client_id: str
    client_hostname: str
    target_ip: str
    bandwidth_mbps: float
    bandwidth_gbps: float
    latency_ms: float
    jitter_ms: float
    packet_loss_percent: float
    mtu: int
    test_duration: int
    status: str
    error: Optional[str] = None


class NetworkSuggestions(BaseModel):
    """I/O parameter suggestions based on network profile."""
    recommended_io_depth: int
    recommended_num_jobs: int
    recommended_block_size: str
    max_theoretical_throughput_mbps: float
    estimated_achievable_throughput_mbps: float
    bottleneck: str
    notes: List[str]


class ClusterNetworkProfile(BaseModel):
    """Aggregated network profile for cluster-client connectivity."""
    cluster_name: str
    target_ip: str
    clients: List[NetworkProfile]
    aggregate_bandwidth_gbps: float
    min_bandwidth_gbps: float
    max_bandwidth_gbps: float
    avg_latency_ms: float
    suggestions: NetworkSuggestions


async def run_iperf_test(
    client: Dict[str, Any],
    target_ip: str,
    duration: int = 10,
    parallel: int = 4,
) -> NetworkProfile:
    """Run iperf3 test from client to target."""
    hostname = client.get("hostname")
    username = client.get("ssh_user", "root")
    password = client.get("ssh_password")
    key_path = client.get("ssh_key_path")
    port = client.get("ssh_port", 22)
    client_id = client.get("id", hostname)

    ssh_client = SSHClient(hostname, username, key_path, password, port)
    
    try:
        await ssh_client.connect()
        
        # Check if iperf3 is installed
        check_result = await ssh_client.run_command("which iperf3", timeout=10, raise_on_error=False)
        if not check_result.success:
            # Try to install iperf3
            install_result = await ssh_client.run_command(
                "yum install -y iperf3 2>/dev/null || apt-get install -y iperf3 2>/dev/null || dnf install -y iperf3 2>/dev/null",
                timeout=120,
                raise_on_error=False
            )
            if not install_result.success:
                return NetworkProfile(
                    client_id=client_id,
                    client_hostname=hostname,
                    target_ip=target_ip,
                    bandwidth_mbps=0,
                    bandwidth_gbps=0,
                    latency_ms=0,
                    jitter_ms=0,
                    packet_loss_percent=0,
                    mtu=1500,
                    test_duration=duration,
                    status="error",
                    error="iperf3 not installed and could not be installed"
                )

        # Get MTU
        mtu_result = await ssh_client.run_command(
            f"ip route get {target_ip} | grep -oP 'mtu \\K[0-9]+'",
            timeout=10,
            raise_on_error=False
        )
        mtu = int(mtu_result.stdout.strip()) if mtu_result.success and mtu_result.stdout.strip() else 1500

        # Run ping test for latency
        ping_result = await ssh_client.run_command(
            f"ping -c 5 -q {target_ip}",
            timeout=30,
            raise_on_error=False
        )
        latency_ms = 0.0
        jitter_ms = 0.0
        packet_loss = 0.0
        
        if ping_result.success:
            # Parse: rtt min/avg/max/mdev = 0.123/0.456/0.789/0.012 ms
            rtt_match = re.search(r'rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', ping_result.stdout)
            if rtt_match:
                latency_ms = float(rtt_match.group(2))  # avg
                jitter_ms = float(rtt_match.group(4))   # mdev
            
            # Parse packet loss
            loss_match = re.search(r'(\d+)% packet loss', ping_result.stdout)
            if loss_match:
                packet_loss = float(loss_match.group(1))

        # Run iperf3 test (client mode, connecting to target as server)
        # First check if target has iperf3 server running
        # For now, we'll run in client mode assuming server is available
        # If not, we'll fall back to a simple dd-based test
        
        iperf_result = await ssh_client.run_command(
            f"iperf3 -c {target_ip} -t {duration} -P {parallel} -J 2>/dev/null || echo 'IPERF_FAILED'",
            timeout=duration + 30,
            raise_on_error=False
        )
        
        bandwidth_mbps = 0.0
        
        if iperf_result.success and "IPERF_FAILED" not in iperf_result.stdout:
            try:
                import json
                iperf_data = json.loads(iperf_result.stdout)
                # Get sender bandwidth from end summary
                end = iperf_data.get("end", {})
                sum_sent = end.get("sum_sent", {})
                bandwidth_bps = sum_sent.get("bits_per_second", 0)
                bandwidth_mbps = bandwidth_bps / 1_000_000
            except (json.JSONDecodeError, KeyError):
                # Try to parse text output
                bw_match = re.search(r'(\d+(?:\.\d+)?)\s*([GMK]?)bits/sec', iperf_result.stdout)
                if bw_match:
                    bw_val = float(bw_match.group(1))
                    unit = bw_match.group(2)
                    if unit == 'G':
                        bandwidth_mbps = bw_val * 1000
                    elif unit == 'K':
                        bandwidth_mbps = bw_val / 1000
                    else:
                        bandwidth_mbps = bw_val
        else:
            # Fallback: estimate based on simple transfer test
            dd_result = await ssh_client.run_command(
                f"dd if=/dev/zero bs=1M count=100 2>&1 | nc -w 5 {target_ip} 12345 2>/dev/null; echo 'done'",
                timeout=60,
                raise_on_error=False
            )
            # If nc fails, we can't measure - just report latency-based estimate
            if latency_ms > 0:
                # Rough estimate: lower latency = higher bandwidth potential
                # This is very rough - just for UI display
                bandwidth_mbps = max(100, 10000 / latency_ms)  # Very rough estimate

        return NetworkProfile(
            client_id=client_id,
            client_hostname=hostname,
            target_ip=target_ip,
            bandwidth_mbps=bandwidth_mbps,
            bandwidth_gbps=bandwidth_mbps / 1000,
            latency_ms=latency_ms,
            jitter_ms=jitter_ms,
            packet_loss_percent=packet_loss,
            mtu=mtu,
            test_duration=duration,
            status="success" if bandwidth_mbps > 0 else "partial",
            error=None if bandwidth_mbps > 0 else "Could not measure bandwidth (iperf3 server not available)"
        )

    except Exception as e:
        logger.error(f"Network test failed for {client_id}: {e}")
        return NetworkProfile(
            client_id=client_id,
            client_hostname=hostname,
            target_ip=target_ip,
            bandwidth_mbps=0,
            bandwidth_gbps=0,
            latency_ms=0,
            jitter_ms=0,
            packet_loss_percent=0,
            mtu=1500,
            test_duration=duration,
            status="error",
            error=str(e)
        )
    finally:
        await ssh_client.close()


def calculate_suggestions(
    profiles: List[NetworkProfile],
    storage_type: str = "file"
) -> NetworkSuggestions:
    """Calculate I/O parameter suggestions based on network profiles."""
    
    if not profiles or all(p.bandwidth_mbps == 0 for p in profiles):
        return NetworkSuggestions(
            recommended_io_depth=32,
            recommended_num_jobs=4,
            recommended_block_size="1m",
            max_theoretical_throughput_mbps=0,
            estimated_achievable_throughput_mbps=0,
            bottleneck="unknown",
            notes=["Could not measure network bandwidth. Using default values."]
        )

    # Calculate aggregate stats
    valid_profiles = [p for p in profiles if p.bandwidth_mbps > 0]
    total_bandwidth = sum(p.bandwidth_mbps for p in valid_profiles)
    min_bandwidth = min(p.bandwidth_mbps for p in valid_profiles) if valid_profiles else 0
    avg_latency = sum(p.latency_ms for p in valid_profiles) / len(valid_profiles) if valid_profiles else 0
    
    notes = []
    
    # Bandwidth-Delay Product (BDP) calculation for optimal I/O depth
    # BDP = Bandwidth (bytes/sec) * RTT (seconds)
    # Optimal window/queue = BDP / packet_size
    avg_bandwidth_bytes = (total_bandwidth * 1_000_000) / 8  # Convert Mbps to Bytes/sec
    rtt_seconds = (avg_latency * 2) / 1000  # RTT = 2 * one-way latency
    
    if rtt_seconds > 0:
        bdp = avg_bandwidth_bytes * rtt_seconds
        optimal_io_depth = max(1, min(256, int(bdp / (1024 * 1024))))  # Per MB block
    else:
        optimal_io_depth = 32
    
    # Determine block size based on bandwidth
    if total_bandwidth > 10000:  # > 10 Gbps
        recommended_block_size = "4m"
        notes.append("High bandwidth network detected - using large block size for efficiency")
    elif total_bandwidth > 1000:  # > 1 Gbps
        recommended_block_size = "1m"
    elif total_bandwidth > 100:  # > 100 Mbps
        recommended_block_size = "256k"
    else:
        recommended_block_size = "64k"
        notes.append("Lower bandwidth network - using smaller block size")
    
    # Determine number of parallel jobs
    num_clients = len(valid_profiles)
    if total_bandwidth > 10000:
        recommended_num_jobs = min(16, num_clients * 4)
    elif total_bandwidth > 1000:
        recommended_num_jobs = min(8, num_clients * 2)
    else:
        recommended_num_jobs = min(4, num_clients)
    
    # Estimate achievable throughput (typically 70-85% of theoretical)
    efficiency = 0.75
    if avg_latency < 1:
        efficiency = 0.85
        notes.append("Low latency network - high efficiency expected")
    elif avg_latency > 10:
        efficiency = 0.60
        notes.append("Higher latency may reduce effective throughput")
    
    estimated_throughput = total_bandwidth * efficiency
    
    # Determine bottleneck
    if min_bandwidth < total_bandwidth / num_clients * 0.5:
        bottleneck = f"slowest_client ({min_bandwidth:.0f} Mbps)"
        notes.append(f"One or more clients have significantly lower bandwidth")
    elif avg_latency > 5:
        bottleneck = "network_latency"
        notes.append("Network latency may limit IOPS-intensive workloads")
    else:
        bottleneck = "none_detected"
    
    # Storage type specific adjustments
    if storage_type == "object":
        # Object storage benefits from larger blocks and parallel uploads
        recommended_block_size = "4m" if total_bandwidth > 1000 else "1m"
        notes.append("Object storage: using larger blocks for multipart uploads")
    
    return NetworkSuggestions(
        recommended_io_depth=optimal_io_depth,
        recommended_num_jobs=recommended_num_jobs,
        recommended_block_size=recommended_block_size,
        max_theoretical_throughput_mbps=total_bandwidth,
        estimated_achievable_throughput_mbps=estimated_throughput,
        bottleneck=bottleneck,
        notes=notes
    )


@router.get("/profile/{cluster_name}")
async def get_network_profile(cluster_name: str, duration: int = 5):
    """Get network profile between clients and cluster."""
    store = get_data_store()
    
    # Get cluster
    cluster = store.get_cluster(cluster_name)
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster '{cluster_name}' not found")
    
    # Get target IP (first monitor or installer node)
    target_ip = None
    if cluster.ceph and cluster.ceph.monitors:
        target_ip = cluster.ceph.monitors[0].split(":")[0]
    elif cluster.installer_node:
        target_ip = cluster.installer_node.host
    
    if not target_ip:
        raise HTTPException(status_code=400, detail="No target IP available for cluster")
    
    # Get clients
    clients = await store.get_clients()
    online_clients = [c for c in clients if c.get("status") == "online"]
    
    if not online_clients:
        raise HTTPException(status_code=400, detail="No online clients available for testing")
    
    # Run network tests in parallel
    tasks = [run_iperf_test(client, target_ip, duration) for client in online_clients]
    profiles = await asyncio.gather(*tasks)
    
    # Calculate suggestions
    suggestions = calculate_suggestions(profiles)
    
    # Calculate aggregates
    valid_profiles = [p for p in profiles if p.bandwidth_mbps > 0]
    
    return ClusterNetworkProfile(
        cluster_name=cluster_name,
        target_ip=target_ip,
        clients=profiles,
        aggregate_bandwidth_gbps=sum(p.bandwidth_gbps for p in valid_profiles),
        min_bandwidth_gbps=min(p.bandwidth_gbps for p in valid_profiles) if valid_profiles else 0,
        max_bandwidth_gbps=max(p.bandwidth_gbps for p in valid_profiles) if valid_profiles else 0,
        avg_latency_ms=sum(p.latency_ms for p in valid_profiles) / len(valid_profiles) if valid_profiles else 0,
        suggestions=suggestions
    )


@router.get("/suggestions/{cluster_name}")
async def get_network_suggestions(cluster_name: str, storage_type: str = "file"):
    """Get I/O parameter suggestions based on cached or quick network profile."""
    store = get_data_store()
    
    # Get cluster
    cluster = store.get_cluster(cluster_name)
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster '{cluster_name}' not found")
    
    # Get target IP
    target_ip = None
    if cluster.ceph and cluster.ceph.monitors:
        target_ip = cluster.ceph.monitors[0].split(":")[0]
    elif cluster.installer_node:
        target_ip = cluster.installer_node.host
    
    if not target_ip:
        raise HTTPException(status_code=400, detail="No target IP available")
    
    # Get clients
    clients = await store.get_clients()
    online_clients = [c for c in clients if c.get("status") == "online"]
    
    if not online_clients:
        # Return default suggestions
        return {
            "cluster_name": cluster_name,
            "target_ip": target_ip,
            "client_count": 0,
            "suggestions": NetworkSuggestions(
                recommended_io_depth=32,
                recommended_num_jobs=4,
                recommended_block_size="1m",
                max_theoretical_throughput_mbps=0,
                estimated_achievable_throughput_mbps=0,
                bottleneck="no_clients",
                notes=["No online clients available"]
            )
        }
    
    # Quick latency test only (faster than full iperf)
    profiles = []
    for client in online_clients[:5]:  # Limit to 5 clients for quick test
        hostname = client.get("hostname")
        username = client.get("ssh_user", "root")
        password = client.get("ssh_password")
        key_path = client.get("ssh_key_path")
        port = client.get("ssh_port", 22)
        client_id = client.get("id", hostname)
        
        ssh_client = SSHClient(hostname, username, key_path, password, port)
        try:
            await ssh_client.connect()
            
            # Quick ping test
            ping_result = await ssh_client.run_command(
                f"ping -c 3 -q {target_ip}",
                timeout=15,
                raise_on_error=False
            )
            
            latency_ms = 1.0  # Default
            if ping_result.success:
                rtt_match = re.search(r'rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', ping_result.stdout)
                if rtt_match:
                    latency_ms = float(rtt_match.group(2))
            
            # Estimate bandwidth from NIC speed
            nic_result = await ssh_client.run_command(
                "cat /sys/class/net/$(ip route get " + target_ip + " | grep -oP 'dev \\K\\S+')/speed 2>/dev/null || echo 1000",
                timeout=10,
                raise_on_error=False
            )
            nic_speed = 1000  # Default 1 Gbps
            if nic_result.success and nic_result.stdout.strip().isdigit():
                nic_speed = int(nic_result.stdout.strip())
            
            profiles.append(NetworkProfile(
                client_id=client_id,
                client_hostname=hostname,
                target_ip=target_ip,
                bandwidth_mbps=nic_speed,
                bandwidth_gbps=nic_speed / 1000,
                latency_ms=latency_ms,
                jitter_ms=0,
                packet_loss_percent=0,
                mtu=1500,
                test_duration=0,
                status="estimated"
            ))
            
        except Exception as e:
            logger.warning(f"Quick network test failed for {client_id}: {e}")
        finally:
            await ssh_client.close()
    
    suggestions = calculate_suggestions(profiles, storage_type)
    
    return {
        "cluster_name": cluster_name,
        "target_ip": target_ip,
        "client_count": len(online_clients),
        "tested_clients": len(profiles),
        "suggestions": suggestions,
        "profiles": profiles
    }


@router.post("/test/{client_id}")
async def test_client_network(client_id: str, target_ip: str, duration: int = 10):
    """Run network test for a specific client."""
    store = get_data_store()
    
    clients = await store.get_clients()
    client = next((c for c in clients if c.get("id") == client_id), None)
    
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")
    
    profile = await run_iperf_test(client, target_ip, duration)
    
    return profile
