"""Common data models for the Scale Testing Framework."""

from common.models.cluster import ClusterConfig, StorageType, StorageBackend
from common.models.client import Client, ClientStatus
from common.models.workload import WorkloadConfig, IOPattern, WorkloadTool
from common.models.metrics import Metrics, AggregatedMetrics, LatencyStats
from common.models.execution import Execution, ExecutionStatus, ExecutionPhase

__all__ = [
    "ClusterConfig",
    "StorageType",
    "StorageBackend",
    "Client",
    "ClientStatus",
    "WorkloadConfig",
    "IOPattern",
    "WorkloadTool",
    "Metrics",
    "AggregatedMetrics",
    "LatencyStats",
    "Execution",
    "ExecutionStatus",
    "ExecutionPhase",
]
