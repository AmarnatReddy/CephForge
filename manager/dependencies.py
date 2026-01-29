"""Dependency injection for the manager."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from manager.storage.data_store import DataStore
    from common.messaging.redis_client import RedisClient

# These will be set by main.py during startup
_data_store = None
_redis_client = None


def set_data_store(store) -> None:
    """Set the global data store instance."""
    global _data_store
    _data_store = store


def set_redis_client(client) -> None:
    """Set the global Redis client instance."""
    global _redis_client
    _redis_client = client


def get_data_store():
    """Get the global data store instance."""
    if _data_store is None:
        raise RuntimeError("Data store not initialized")
    return _data_store


def get_redis_client():
    """Get the global Redis client instance."""
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized")
    return _redis_client
