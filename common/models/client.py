"""Client node models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Tuple
from pydantic import BaseModel, Field


class ClientStatus(str, Enum):
    """Client connection status."""
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    ERROR = "error"
    UNREACHABLE = "unreachable"


class SSHConfig(BaseModel):
    """SSH connection configuration for a client."""
    user: str = Field(default="root", description="SSH username")
    key_path: Optional[str] = Field(default=None, description="Path to SSH private key")
    password: Optional[str] = Field(default=None, description="SSH password (if no key)")
    port: int = Field(default=22, description="SSH port")
    timeout: int = Field(default=10, description="Connection timeout in seconds")


class ClientResources(BaseModel):
    """Client resource information."""
    cpu_cores: Optional[int] = Field(default=None, description="Number of CPU cores")
    memory_gb: Optional[float] = Field(default=None, description="Total memory in GB")
    disk_free_gb: Optional[float] = Field(default=None, description="Free disk space in GB")
    network_speed_gbps: Optional[float] = Field(default=None, description="Network speed in Gbps")


class Client(BaseModel):
    """Client node configuration and status."""
    id: str = Field(..., description="Unique client identifier")
    hostname: str = Field(..., description="Hostname or IP address")
    
    # SSH configuration
    ssh: SSHConfig = Field(default_factory=SSHConfig)
    
    # Status
    status: ClientStatus = Field(default=ClientStatus.UNKNOWN)
    agent_version: Optional[str] = Field(default=None)
    agent_port: int = Field(default=8080, description="Agent HTTP port")
    
    # Timestamps
    registered_at: Optional[datetime] = Field(default=None)
    last_heartbeat: Optional[datetime] = Field(default=None)
    
    # Capabilities
    installed_tools: list[str] = Field(default_factory=list)
    supported_workloads: list[str] = Field(default_factory=list)
    
    # Resources
    resources: Optional[ClientResources] = Field(default=None)
    
    # Current execution
    current_execution_id: Optional[str] = Field(default=None)
    
    # Tags and metadata
    tags: dict[str, str] = Field(default_factory=dict)
    
    @property
    def is_available(self) -> bool:
        """Check if client is available for new workloads."""
        return self.status == ClientStatus.ONLINE and self.current_execution_id is None


class ClientHealth(BaseModel):
    """Client health check result."""
    client_id: str
    hostname: str
    status: ClientStatus
    
    # Connectivity
    ssh_reachable: bool = False
    ssh_latency_ms: Optional[float] = None
    
    # Agent
    agent_running: bool = False
    agent_version: Optional[str] = None
    agent_responsive: bool = False
    
    # System
    uptime_seconds: Optional[int] = None
    load_average: Optional[tuple[float, float, float]] = None
    memory_available_gb: Optional[float] = None
    disk_free_gb: Optional[float] = None
    
    # Tools
    tools_installed: dict[str, bool] = Field(default_factory=dict)
    missing_tools: list[str] = Field(default_factory=list)
    
    # Storage
    storage_accessible: bool = False
    mount_points_ok: list[str] = Field(default_factory=list)
    mount_points_failed: list[str] = Field(default_factory=list)
    
    # Network to storage
    network_latency_ms: Optional[float] = None
    network_bandwidth_mbps: Optional[float] = None
    
    # Errors
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    
    @property
    def is_healthy(self) -> bool:
        """Check if client passed all critical health checks."""
        return (
            self.ssh_reachable
            and self.agent_running
            and self.agent_responsive
            and len(self.missing_tools) == 0
            and len(self.errors) == 0
        )
