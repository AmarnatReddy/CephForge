"""Event definitions for messaging between manager and agents."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional, Dict
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of events in the system."""
    
    # Agent lifecycle
    AGENT_REGISTER = "agent.register"
    AGENT_HEARTBEAT = "agent.heartbeat"
    AGENT_DISCONNECT = "agent.disconnect"
    
    # Execution control
    EXECUTION_PREPARE = "execution.prepare"
    EXECUTION_START = "execution.start"
    EXECUTION_STOP = "execution.stop"
    EXECUTION_PAUSE = "execution.pause"
    EXECUTION_RESUME = "execution.resume"
    EXECUTION_SCALE = "execution.scale"
    
    # Status updates
    STATUS_UPDATE = "status.update"
    STATUS_READY = "status.ready"
    STATUS_ERROR = "status.error"
    
    # Metrics
    METRICS_REPORT = "metrics.report"
    METRICS_AGGREGATE = "metrics.aggregate"
    
    # Prechecks
    PRECHECK_REQUEST = "precheck.request"
    PRECHECK_RESULT = "precheck.result"
    
    # Commands
    COMMAND_REQUEST = "command.request"
    COMMAND_RESULT = "command.result"


class Event(BaseModel):
    """Base event structure for all messages."""
    
    type: EventType = Field(..., description="Event type")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str = Field(..., description="Source identifier (agent_id or 'manager')")
    target: Optional[str] = Field(
        default=None,
        description="Target identifier (agent_id, 'all', or None for manager)"
    )
    execution_id: Optional[str] = Field(default=None)
    payload: dict[str, Any] = Field(default_factory=dict)
    
    def to_json(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "target": self.target,
            "execution_id": self.execution_id,
            "payload": self.payload,
        }
    
    @classmethod
    def from_json(cls, data: dict) -> "Event":
        """Create event from JSON dict."""
        return cls(
            type=EventType(data["type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source=data["source"],
            target=data.get("target"),
            execution_id=data.get("execution_id"),
            payload=data.get("payload", {}),
        )


# Convenience functions for creating common events

def create_heartbeat_event(agent_id: str, status: str, metrics: dict = None) -> Event:
    """Create an agent heartbeat event."""
    return Event(
        type=EventType.AGENT_HEARTBEAT,
        source=agent_id,
        target="manager",
        payload={
            "status": status,
            "metrics": metrics or {},
        },
    )


def create_register_event(
    agent_id: str,
    hostname: str,
    version: str,
    capabilities: dict = None
) -> Event:
    """Create an agent registration event."""
    return Event(
        type=EventType.AGENT_REGISTER,
        source=agent_id,
        target="manager",
        payload={
            "hostname": hostname,
            "version": version,
            "capabilities": capabilities or {},
        },
    )


def create_execution_start_event(
    execution_id: str,
    target: str,
    config: dict
) -> Event:
    """Create an execution start event."""
    return Event(
        type=EventType.EXECUTION_START,
        source="manager",
        target=target,
        execution_id=execution_id,
        payload={"config": config},
    )


def create_execution_stop_event(execution_id: str, target: str = "all") -> Event:
    """Create an execution stop event."""
    return Event(
        type=EventType.EXECUTION_STOP,
        source="manager",
        target=target,
        execution_id=execution_id,
    )


def create_metrics_event(
    agent_id: str,
    execution_id: str,
    metrics: dict
) -> Event:
    """Create a metrics report event."""
    return Event(
        type=EventType.METRICS_REPORT,
        source=agent_id,
        target="manager",
        execution_id=execution_id,
        payload={"metrics": metrics},
    )


def create_status_event(
    agent_id: str,
    execution_id: str,
    status: str,
    message: str = ""
) -> Event:
    """Create a status update event."""
    return Event(
        type=EventType.STATUS_UPDATE,
        source=agent_id,
        target="manager",
        execution_id=execution_id,
        payload={
            "status": status,
            "message": message,
        },
    )


def create_error_event(
    source: str,
    execution_id: str = None,
    error: str = "",
    details: dict = None
) -> Event:
    """Create an error event."""
    return Event(
        type=EventType.STATUS_ERROR,
        source=source,
        target="manager",
        execution_id=execution_id,
        payload={
            "error": error,
            "details": details or {},
        },
    )
