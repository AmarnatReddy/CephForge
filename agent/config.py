"""Agent configuration settings."""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


def get_default_agent_id() -> str:
    """Generate a default agent ID from hostname."""
    hostname = socket.gethostname()
    return f"agent_{hostname}"


class AgentSettings(BaseSettings):
    """Agent settings loaded from environment variables."""
    
    # Agent identification
    agent_id: str = Field(default_factory=get_default_agent_id)
    
    # Manager connection
    manager_url: str = "http://localhost:8000"
    redis_url: str = "redis://localhost:6379"
    
    # Agent HTTP server
    host: str = "0.0.0.0"
    port: int = 8080
    
    # Heartbeat
    heartbeat_interval: int = 5  # seconds
    
    # Metrics
    metrics_interval: int = 1  # seconds
    
    # Work directory
    work_dir: Path = Field(default=Path("/tmp/scale_agent"))
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_prefix = "SCALE_AGENT_"
        env_file = ".env"
    
    @property
    def hostname(self) -> str:
        return socket.gethostname()
    
    @property
    def ip_address(self) -> str:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


# Global settings instance
_settings: Optional[AgentSettings] = None


def get_settings() -> AgentSettings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = AgentSettings()
    return _settings


def init_settings(**kwargs) -> AgentSettings:
    """Initialize settings with custom values."""
    global _settings
    _settings = AgentSettings(**kwargs)
    return _settings
