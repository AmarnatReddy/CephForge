"""System management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from manager.config import get_settings, Settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """Check system health."""
    return {
        "status": "healthy",
        "components": {
            "api": "healthy",
            "database": "healthy",
            "redis": "healthy",
        }
    }


@router.get("/config")
async def get_config():
    """Get system configuration (non-sensitive)."""
    settings = get_settings()
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "data_path": str(settings.data_path),
        "agent_heartbeat_interval": settings.agent_heartbeat_interval,
        "agent_heartbeat_timeout": settings.agent_heartbeat_timeout,
        "default_metrics_interval": settings.default_metrics_interval,
    }


@router.get("/version")
async def get_version():
    """Get application version."""
    settings = get_settings()
    return {
        "name": settings.app_name,
        "version": settings.app_version,
    }
