"""Network profiler for optimal I/O parameter tuning."""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Optional, Dict

logger = logging.getLogger(__name__)


@dataclass
class NetworkProfile:
    """Network profile for a client."""
    interface: str
    speed_gbps: float
    mtu: int
    baseline_bandwidth_mbps: float
    latency_ms: float
    tcp_buffer_size: int
    recommended_io_depth: int
    recommended_block_size: str
    recommended_jobs: int


class NetworkProfiler:
    """Profile network capabilities and calculate optimal I/O parameters."""
    
    def __init__(self, storage_endpoint: str = ""):
        self.storage_endpoint = storage_endpoint
    
    def get_interface_speed(self, interface: str = None) -> float:
        """Get network interface speed in Gbps."""
        interface = interface or self._get_default_interface()
        
        try:
            result = subprocess.run(
                ["ethtool", interface],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            match = re.search(r"Speed:\s*(\d+)(M|G)b/s", result.stdout)
            if match:
                speed = int(match.group(1))
                unit = match.group(2)
                if unit == "M":
                    return speed / 1000
                return float(speed)
                
        except Exception as e:
            logger.warning(f"Failed to get interface speed: {e}")
        
        # Try sysfs as fallback
        try:
            with open(f"/sys/class/net/{interface}/speed") as f:
                speed_mbps = int(f.read().strip())
                return speed_mbps / 1000
        except Exception:
            pass
        
        return 1.0  # Default 1 Gbps
    
    def get_mtu(self, interface: str = None) -> int:
        """Get interface MTU."""
        interface = interface or self._get_default_interface()
        
        try:
            with open(f"/sys/class/net/{interface}/mtu") as f:
                return int(f.read().strip())
        except Exception:
            return 1500
    
    async def measure_bandwidth(self, duration: int = 10) -> float:
        """Measure baseline bandwidth using iperf3."""
        if not self.storage_endpoint:
            logger.warning("No storage endpoint for bandwidth test")
            return 0
        
        try:
            process = await asyncio.create_subprocess_exec(
                "iperf3", "-c", self.storage_endpoint,
                "-t", str(duration), "-J",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=duration + 10,
            )
            
            if process.returncode == 0:
                import json
                result = json.loads(stdout.decode())
                bps = result.get("end", {}).get("sum_received", {}).get("bits_per_second", 0)
                return bps / 1_000_000  # Return Mbps
                
        except asyncio.TimeoutError:
            logger.warning("iperf3 bandwidth test timed out")
        except FileNotFoundError:
            logger.warning("iperf3 not installed")
        except Exception as e:
            logger.warning(f"Bandwidth measurement failed: {e}")
        
        return 0
    
    async def measure_latency(self) -> float:
        """Measure network latency using ping."""
        if not self.storage_endpoint:
            return 0
        
        try:
            process = await asyncio.create_subprocess_exec(
                "ping", "-c", "10", "-q", self.storage_endpoint,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=15,
            )
            
            match = re.search(r"= [\d.]+/([\d.]+)/", stdout.decode())
            if match:
                return float(match.group(1))
                
        except Exception as e:
            logger.warning(f"Latency measurement failed: {e}")
        
        return 1.0  # Default 1ms
    
    def calculate_optimal_params(self, profile: NetworkProfile) -> dict:
        """Calculate optimal I/O parameters based on network profile."""
        # Bandwidth-Delay Product (BDP) in bytes
        bdp = int((profile.baseline_bandwidth_mbps * 1_000_000 / 8) * (profile.latency_ms / 1000))
        
        # Optimal IO depth based on BDP and block size
        block_size_bytes = 4096  # Assume 4K default
        optimal_io_depth = max(1, min(256, bdp // block_size_bytes))
        
        # Optimal block size based on MTU
        if profile.mtu >= 9000:
            optimal_bs = "128k"
        elif profile.mtu >= 4000:
            optimal_bs = "64k"
        else:
            optimal_bs = "4k"
        
        # Optimal number of jobs based on bandwidth
        if profile.speed_gbps >= 100:
            optimal_jobs = 16
        elif profile.speed_gbps >= 25:
            optimal_jobs = 8
        elif profile.speed_gbps >= 10:
            optimal_jobs = 4
        else:
            optimal_jobs = 2
        
        return {
            "io_depth": optimal_io_depth,
            "block_size": optimal_bs,
            "num_jobs": optimal_jobs,
            "tcp_buffer_size": max(bdp, 65536),
        }
    
    async def full_profile(self) -> NetworkProfile:
        """Run full network profiling."""
        interface = self._get_default_interface()
        
        speed = self.get_interface_speed(interface)
        mtu = self.get_mtu(interface)
        
        bandwidth = await self.measure_bandwidth(duration=5)
        latency = await self.measure_latency()
        
        tcp_buffer = self._get_tcp_buffer_size()
        
        # Calculate optimal parameters
        profile = NetworkProfile(
            interface=interface,
            speed_gbps=speed,
            mtu=mtu,
            baseline_bandwidth_mbps=bandwidth or (speed * 1000 * 0.8),
            latency_ms=latency,
            tcp_buffer_size=tcp_buffer,
            recommended_io_depth=32,
            recommended_block_size="4k",
            recommended_jobs=4,
        )
        
        optimal = self.calculate_optimal_params(profile)
        profile.recommended_io_depth = optimal["io_depth"]
        profile.recommended_block_size = optimal["block_size"]
        profile.recommended_jobs = optimal["num_jobs"]
        
        return profile
    
    def _get_default_interface(self) -> str:
        """Get the default network interface."""
        try:
            result = subprocess.run(
                ["ip", "route", "get", "8.8.8.8"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            match = re.search(r"dev\s+(\S+)", result.stdout)
            if match:
                return match.group(1)
                
        except Exception:
            pass
        
        # Fallback: look for common interface names
        import os
        for iface in ["eth0", "ens0", "enp0s0", "eno1"]:
            if os.path.exists(f"/sys/class/net/{iface}"):
                return iface
        
        return "eth0"
    
    def _get_tcp_buffer_size(self) -> int:
        """Get current TCP buffer size."""
        try:
            with open("/proc/sys/net/core/rmem_max") as f:
                return int(f.read().strip())
        except Exception:
            return 212992  # Linux default
