"""Manager configuration settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, List

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    app_name: str = "Scale Testing Framework"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Data storage
    data_path: Path = Field(default=Path("./data"))
    
    # Redis
    redis_url: str = "redis://localhost:6379"
    
    # Agent settings
    agent_heartbeat_interval: int = 5  # seconds
    agent_heartbeat_timeout: int = 30  # seconds
    
    # Execution settings
    default_metrics_interval: int = 1  # seconds
    max_concurrent_executions: int = 1  # single executor
    
    # Precheck settings
    precheck_ssh_timeout: int = 10  # seconds
    precheck_command_timeout: int = 60  # seconds
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # CORS
    cors_origins: list[str] = ["*"]
    
    class Config:
        env_prefix = "SCALE_"
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @property
    def database_path(self) -> Path:
        return self.data_path / "scale.db"
    
    @property
    def config_path(self) -> Path:
        return self.data_path / "config"
    
    @property
    def executions_path(self) -> Path:
        return self.data_path / "executions"
    
    @property
    def logs_path(self) -> Path:
        return self.data_path / "logs"


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def init_settings(**kwargs) -> Settings:
    """Initialize settings with custom values."""
    global _settings
    _settings = Settings(**kwargs)
    return _settings
