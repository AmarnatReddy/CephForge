"""Pytest configuration and shared fixtures."""

import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import aiosqlite

from manager.storage.data_store import DataStore
from common.messaging.redis_client import RedisClient


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def data_store(temp_dir: Path) -> DataStore:
    """Create a DataStore instance with temporary directory."""
    return DataStore(temp_dir)


@pytest.fixture
def mock_redis_client() -> MagicMock:
    """Create a mock Redis client."""
    mock = MagicMock(spec=RedisClient)
    mock.publish = AsyncMock(return_value=1)
    mock.publish_to_agent = AsyncMock(return_value=1)
    mock.publish_to_manager = AsyncMock(return_value=1)
    mock.publish_broadcast = AsyncMock(return_value=1)
    mock.publish_metrics = AsyncMock(return_value=1)
    mock.connect = AsyncMock()
    mock.disconnect = AsyncMock()
    mock.subscribe = AsyncMock()
    mock.subscribe_pattern = AsyncMock()
    mock.start_listening = AsyncMock()
    mock.set = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.delete = AsyncMock(return_value=1)
    mock.hset = AsyncMock(return_value=1)
    mock.hget = AsyncMock(return_value=None)
    mock.hgetall = AsyncMock(return_value={})
    mock.expire = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_cluster_config() -> dict:
    """Sample cluster configuration."""
    return {
        "name": "test-cluster",
        "storage_type": "block",
        "backend": "ceph_rbd",
        "ceph": {
            "monitors": ["192.168.1.10:6789"],
            "user": "admin",
            "keyring_path": "/etc/ceph/ceph.client.admin.keyring",
            "conf_path": "/etc/ceph/ceph.conf",
        },
    }


@pytest.fixture
def sample_client_config() -> dict:
    """Sample client configuration."""
    return {
        "id": "client-1",
        "hostname": "192.168.1.100",
        "ssh": {
            "user": "root",
            "port": 22,
        },
    }


@pytest.fixture
def sample_workload_config() -> dict:
    """Sample workload configuration."""
    return {
        "name": "test-workload",
        "cluster_name": "test-cluster",
        "storage_type": "block",
        "tool": "fio",
        "io": {
            "pattern": "random",
            "block_size": "4k",
            "read_percent": 100,
            "io_depth": 32,
            "num_jobs": 1,
        },
        "test": {
            "duration": 60,
            "file_size": "1G",
        },
        "clients": {
            "mode": "all",
        },
    }


@pytest.fixture
def sample_execution_config() -> dict:
    """Sample execution configuration."""
    return {
        "name": "test-execution",
        "workload_config": {
            "name": "test-workload",
            "cluster_name": "test-cluster",
            "storage_type": "block",
            "tool": "fio",
        },
        "cluster_config": {
            "name": "test-cluster",
            "storage_type": "block",
            "backend": "ceph_rbd",
        },
    }
