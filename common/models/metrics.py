"""Metrics and performance data models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, List
from pydantic import BaseModel, Field


class LatencyStats(BaseModel):
    """Latency statistics in microseconds."""
    avg: float = Field(default=0, description="Average latency")
    min: float = Field(default=0, description="Minimum latency")
    max: float = Field(default=0, description="Maximum latency")
    p50: float = Field(default=0, description="50th percentile")
    p90: float = Field(default=0, description="90th percentile")
    p95: float = Field(default=0, description="95th percentile")
    p99: float = Field(default=0, description="99th percentile")
    p999: float = Field(default=0, description="99.9th percentile")


class IOPSStats(BaseModel):
    """IOPS statistics."""
    read: int = Field(default=0, description="Read IOPS")
    write: int = Field(default=0, description="Write IOPS")
    total: int = Field(default=0, description="Total IOPS")


class ThroughputStats(BaseModel):
    """Throughput statistics in bytes per second."""
    read_bps: int = Field(default=0, description="Read bytes per second")
    write_bps: int = Field(default=0, description="Write bytes per second")
    total_bps: int = Field(default=0, description="Total bytes per second")
    
    @property
    def read_mbps(self) -> float:
        """Read throughput in MB/s."""
        return self.read_bps / (1024 * 1024)
    
    @property
    def write_mbps(self) -> float:
        """Write throughput in MB/s."""
        return self.write_bps / (1024 * 1024)
    
    @property
    def total_mbps(self) -> float:
        """Total throughput in MB/s."""
        return self.total_bps / (1024 * 1024)
    
    @property
    def total_gbps(self) -> float:
        """Total throughput in Gbps."""
        return (self.total_bps * 8) / (1000 * 1000 * 1000)


class NetworkStats(BaseModel):
    """Network utilization statistics."""
    rx_bytes: int = Field(default=0, description="Received bytes")
    tx_bytes: int = Field(default=0, description="Transmitted bytes")
    rx_rate_mbps: float = Field(default=0, description="Receive rate in Mbps")
    tx_rate_mbps: float = Field(default=0, description="Transmit rate in Mbps")
    utilization_percent: float = Field(default=0, description="Network utilization %")


class Metrics(BaseModel):
    """Single metrics sample from a client."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    client_id: str = Field(..., description="Client identifier")
    execution_id: str = Field(..., description="Execution identifier")
    
    # Performance metrics
    iops: IOPSStats = Field(default_factory=IOPSStats)
    throughput: ThroughputStats = Field(default_factory=ThroughputStats)
    latency_us: LatencyStats = Field(default_factory=LatencyStats)
    
    # Network metrics
    network: Optional[NetworkStats] = Field(default=None)
    
    # System metrics
    cpu_percent: Optional[float] = Field(default=None)
    memory_percent: Optional[float] = Field(default=None)
    
    # Errors
    io_errors: int = Field(default=0)
    
    def to_jsonl(self) -> dict:
        """Convert to JSON Lines format (compact)."""
        return {
            "ts": self.timestamp.isoformat(),
            "client": self.client_id,
            "iops": {"r": self.iops.read, "w": self.iops.write},
            "bw": {"r": self.throughput.read_bps, "w": self.throughput.write_bps},
            "lat_us": {
                "avg": self.latency_us.avg,
                "p99": self.latency_us.p99,
            },
            "errors": self.io_errors,
        }


class AggregatedMetrics(BaseModel):
    """Aggregated metrics across all clients."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    execution_id: str = Field(..., description="Execution identifier")
    
    # Aggregate performance
    iops: IOPSStats = Field(default_factory=IOPSStats)
    throughput: ThroughputStats = Field(default_factory=ThroughputStats)
    latency_us: LatencyStats = Field(default_factory=LatencyStats)
    
    # Client info
    active_clients: int = Field(default=0)
    total_clients: int = Field(default=0)
    
    # Per-client breakdown (client_id -> metrics)
    client_metrics: dict[str, Metrics] = Field(default_factory=dict)
    
    # Network aggregate
    total_network_gbps: float = Field(default=0)
    network_utilization_percent: float = Field(default=0)
    
    # Errors
    total_errors: int = Field(default=0)
    error_rate_percent: float = Field(default=0)
    
    def to_jsonl(self) -> dict:
        """Convert to JSON Lines format (compact)."""
        return {
            "ts": self.timestamp.isoformat(),
            "iops": {"r": self.iops.read, "w": self.iops.write, "t": self.iops.total},
            "bw_mbps": {
                "r": round(self.throughput.read_mbps, 2),
                "w": round(self.throughput.write_mbps, 2),
                "t": round(self.throughput.total_mbps, 2),
            },
            "lat_us": {
                "avg": round(self.latency_us.avg, 2),
                "p50": round(self.latency_us.p50, 2),
                "p99": round(self.latency_us.p99, 2),
            },
            "clients": self.active_clients,
            "net_gbps": round(self.total_network_gbps, 2),
            "errors": self.total_errors,
        }


class ExecutionSummary(BaseModel):
    """Final execution summary with aggregate results."""
    execution_id: str
    name: str
    status: str
    
    # Timing
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: int = 0
    ramp_time_seconds: int = 0
    
    # Configuration summary
    storage_type: str
    backend: str
    workload_tool: str
    block_size: str
    io_pattern: str
    read_percent: int
    
    # Client summary
    clients_requested: int
    clients_active: int
    clients_excluded: list[str] = Field(default_factory=list)
    
    # Results
    iops: IOPSStats = Field(default_factory=IOPSStats)
    throughput: ThroughputStats = Field(default_factory=ThroughputStats)
    latency_us: LatencyStats = Field(default_factory=LatencyStats)
    
    # Averages
    iops_per_client: float = 0
    throughput_per_client_mbps: float = 0
    
    # Network
    aggregate_bandwidth_gbps: float = 0
    network_utilization_percent: float = 0
    
    # Errors
    total_errors: int = 0
    error_rate_percent: float = 0
