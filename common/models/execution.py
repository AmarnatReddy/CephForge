"""Execution models for test runs."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List
from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Execution status states."""
    PENDING = "pending"
    PRECHECKS = "prechecks"
    PREPARING = "preparing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionPhase(str, Enum):
    """Current execution phase."""
    INIT = "init"
    PRECHECK = "precheck"
    PREPARE = "prepare"
    RAMP_UP = "ramp_up"
    STEADY_STATE = "steady_state"
    RAMP_DOWN = "ramp_down"
    CLEANUP = "cleanup"
    DONE = "done"


class ClientExecutionState(BaseModel):
    """State of a client within an execution."""
    client_id: str
    status: str = "pending"  # pending, preparing, running, stopped, failed
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    current_iops: int = 0
    current_throughput_mbps: float = 0
    current_latency_us: float = 0
    total_errors: int = 0
    error_message: Optional[str] = None


class Execution(BaseModel):
    """Test execution state."""
    id: str = Field(..., description="Unique execution identifier")
    name: str = Field(..., description="Execution name")
    
    # Status
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING)
    phase: ExecutionPhase = Field(default=ExecutionPhase.INIT)
    
    # Workload reference
    workload_name: str = Field(..., description="Name of workload config")
    cluster_name: str = Field(..., description="Target cluster name")
    
    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Duration
    planned_duration: int = Field(default=60, description="Planned duration in seconds")
    elapsed_seconds: int = Field(default=0)
    remaining_seconds: int = Field(default=0)
    
    # Progress
    progress_percent: float = Field(default=0, ge=0, le=100)
    
    # Clients
    total_clients: int = Field(default=0)
    active_clients: int = Field(default=0)
    failed_clients: int = Field(default=0)
    client_states: dict[str, ClientExecutionState] = Field(default_factory=dict)
    
    # Current aggregate metrics
    current_iops: int = Field(default=0)
    current_throughput_mbps: float = Field(default=0)
    current_latency_us: float = Field(default=0)
    
    # Errors
    error_count: int = Field(default=0)
    error_messages: list[str] = Field(default_factory=list)
    
    # Paths to data files
    config_path: Optional[str] = None
    metrics_path: Optional[str] = None
    report_path: Optional[str] = None
    log_path: Optional[str] = None
    
    @property
    def is_running(self) -> bool:
        """Check if execution is currently running."""
        return self.status in [ExecutionStatus.RUNNING, ExecutionStatus.PAUSED]
    
    @property
    def is_finished(self) -> bool:
        """Check if execution has finished."""
        return self.status in [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        ]
    
    @property
    def duration_seconds(self) -> int:
        """Calculate actual duration."""
        if self.started_at is None:
            return 0
        end_time = self.completed_at or datetime.utcnow()
        return int((end_time - self.started_at).total_seconds())


class PrecheckResult(BaseModel):
    """Result of a single precheck."""
    name: str
    passed: bool
    severity: str = "info"  # info, warning, critical
    message: str
    details: dict = Field(default_factory=dict)
    raw_output: Optional[str] = None


class PrecheckReport(BaseModel):
    """Complete precheck report."""
    execution_id: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    
    # Overall status
    overall_status: str  # passed, passed_with_warnings, failed
    can_proceed: bool
    
    # Cluster checks
    cluster_health: Optional[str] = None
    cluster_checks: list[PrecheckResult] = Field(default_factory=list)
    
    # Client checks
    clients_total: int = 0
    clients_online: int = 0
    clients_offline: int = 0
    client_results: list[dict] = Field(default_factory=list)
    excluded_clients: list[str] = Field(default_factory=list)
    
    # Custom commands
    custom_command_results: list[dict] = Field(default_factory=list)
    
    # Network baseline
    network_baseline: Optional[dict] = None
    
    # Summary
    warnings: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    proceed_message: str = ""
