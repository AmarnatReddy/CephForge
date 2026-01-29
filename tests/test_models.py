"""Unit tests for Pydantic models."""

import pytest
from datetime import datetime

from common.models.client import Client, ClientStatus, ClientHealth, SSHConfig, ClientResources
from common.models.cluster import (
    ClusterConfig,
    StorageType,
    StorageBackend,
    CephConnection,
    NFSConnection,
    S3Connection,
)
from common.models.workload import (
    WorkloadConfig,
    StorageWorkloadType,
    WorkloadTool,
    IOConfig,
    IOPattern,
    TestConfig,
    ClientSelection,
)
from common.models.execution import Execution, ExecutionStatus, ExecutionPhase
from common.messaging.events import Event, EventType


class TestClientModels:
    """Tests for client models."""
    
    def test_ssh_config_defaults(self):
        """Test SSH config with defaults."""
        config = SSHConfig()
        
        assert config.user == "root"
        assert config.port == 22
        assert config.timeout == 10
        assert config.key_path is None
        assert config.password is None
    
    def test_client_creation(self):
        """Test creating a client."""
        client = Client(
            id="client-1",
            hostname="192.168.1.100",
        )
        
        assert client.id == "client-1"
        assert client.hostname == "192.168.1.100"
        assert client.status == ClientStatus.UNKNOWN
        assert client.is_available is False
    
    def test_client_is_available(self):
        """Test client availability check."""
        client = Client(
            id="client-1",
            hostname="192.168.1.100",
            status=ClientStatus.ONLINE,
        )
        
        assert client.is_available is True
        
        client.current_execution_id = "exec-1"
        assert client.is_available is False
    
    def test_client_health(self):
        """Test client health model."""
        health = ClientHealth(
            client_id="client-1",
            hostname="192.168.1.100",
            status=ClientStatus.ONLINE,
            ssh_reachable=True,
            agent_running=True,
            agent_responsive=True,
        )
        
        assert health.is_healthy is True
        
        health.errors = ["Some error"]
        assert health.is_healthy is False


class TestClusterModels:
    """Tests for cluster models."""
    
    def test_ceph_connection(self):
        """Test Ceph connection model."""
        ceph = CephConnection(monitors=["192.168.1.10:6789"])
        
        assert len(ceph.monitors) == 1
        assert ceph.user == "admin"
        assert ceph.keyring_path == "/etc/ceph/ceph.client.admin.keyring"
    
    def test_nfs_connection(self):
        """Test NFS connection model."""
        nfs = NFSConnection(server="192.168.1.10", export_path="/export")
        
        assert nfs.server == "192.168.1.10"
        assert nfs.export_path == "/export"
        assert nfs.mount_point == "/mnt/nfs_test"
    
    def test_s3_connection(self):
        """Test S3 connection model."""
        s3 = S3Connection(
            endpoint="https://s3.example.com",
            access_key="access",
            secret_key="secret",
            bucket="test-bucket",
        )
        
        assert s3.endpoint == "https://s3.example.com"
        assert s3.use_ssl is True
        assert s3.verify_ssl is True
    
    def test_cluster_config_ceph(self):
        """Test cluster config with Ceph backend."""
        cluster = ClusterConfig(
            name="test-cluster",
            storage_type=StorageType.BLOCK,
            backend=StorageBackend.CEPH_RBD,
            ceph=CephConnection(monitors=["192.168.1.10:6789"]),
        )
        
        assert cluster.name == "test-cluster"
        assert cluster.storage_type == StorageType.BLOCK
        assert cluster.get_connection() == cluster.ceph
    
    def test_cluster_config_nfs(self):
        """Test cluster config with NFS backend."""
        cluster = ClusterConfig(
            name="test-cluster",
            storage_type=StorageType.FILE,
            backend=StorageBackend.NFS,
            nfs=NFSConnection(server="192.168.1.10", export_path="/export"),
        )
        
        assert cluster.get_connection() == cluster.nfs
    
    def test_cluster_config_s3(self):
        """Test cluster config with S3 backend."""
        cluster = ClusterConfig(
            name="test-cluster",
            storage_type=StorageType.OBJECT,
            backend=StorageBackend.S3,
            s3=S3Connection(
                endpoint="https://s3.example.com",
                access_key="access",
                secret_key="secret",
                bucket="test-bucket",
            ),
        )
        
        assert cluster.get_connection() == cluster.s3
    
    def test_cluster_config_missing_connection(self):
        """Test cluster config with missing connection."""
        cluster = ClusterConfig(
            name="test-cluster",
            storage_type=StorageType.BLOCK,
            backend=StorageBackend.CEPH_RBD,
        )
        
        with pytest.raises(ValueError):
            cluster.get_connection()


class TestWorkloadModels:
    """Tests for workload models."""
    
    def test_io_config_defaults(self):
        """Test IO config defaults."""
        io = IOConfig()
        
        assert io.pattern == IOPattern.RANDOM
        assert io.block_size == "4k"
        assert io.read_percent == 100
        assert io.write_percent == 0
        assert io.io_depth == 32
    
    def test_io_config_write_percent_validation(self):
        """Test IO config write percent validation."""
        io = IOConfig(read_percent=70, write_percent=30)
        
        assert io.read_percent == 70
        assert io.write_percent == 30
    
    def test_io_config_auto_adjust_write(self):
        """Test IO config auto-adjusts write percent."""
        io = IOConfig(read_percent=80, write_percent=10)
        
        # Should auto-adjust to 20
        assert io.read_percent == 80
        assert io.write_percent == 20
    
    def test_test_config_defaults(self):
        """Test test config defaults."""
        test = TestConfig()
        
        assert test.duration == 60
        assert test.ramp_time == 0
        assert test.file_size == "1G"
    
    def test_workload_config_block(self):
        """Test block workload config."""
        workload = WorkloadConfig(
            name="test-workload",
            cluster_name="test-cluster",
            storage_type=StorageWorkloadType.BLOCK,
        )
        
        assert workload.is_block_workload is True
        assert workload.is_file_workload is False
        assert workload.is_object_workload is False
        assert workload.tool == WorkloadTool.FIO
    
    def test_workload_config_file(self):
        """Test file workload config."""
        from common.models.workload import MountConfig, FilesystemType
        
        workload = WorkloadConfig(
            name="test-workload",
            cluster_name="test-cluster",
            storage_type=StorageWorkloadType.FILE,
            mount=MountConfig(filesystem_type=FilesystemType.CEPHFS),
        )
        
        assert workload.is_file_workload is True
        assert workload.fio_directory == workload.mount.mount_point
    
    def test_client_selection_all(self):
        """Test client selection mode 'all'."""
        selection = ClientSelection(mode="all")
        
        assert selection.mode == "all"
        assert selection.count is None
        assert selection.client_ids == []
    
    def test_client_selection_count(self):
        """Test client selection mode 'count'."""
        selection = ClientSelection(mode="count", count=5)
        
        assert selection.mode == "count"
        assert selection.count == 5
    
    def test_client_selection_specific(self):
        """Test client selection mode 'specific'."""
        selection = ClientSelection(
            mode="specific",
            client_ids=["client-1", "client-2"],
        )
        
        assert selection.mode == "specific"
        assert selection.client_ids == ["client-1", "client-2"]


class TestExecutionModels:
    """Tests for execution models."""
    
    def test_execution_creation(self):
        """Test creating an execution."""
        execution = Execution(
            id="exec-1",
            name="test-execution",
            workload_name="test-workload",
            cluster_name="test-cluster",
        )
        
        assert execution.id == "exec-1"
        assert execution.status == ExecutionStatus.PENDING
        assert execution.phase == ExecutionPhase.INIT
        assert execution.is_running is False
        assert execution.is_finished is False
    
    def test_execution_running(self):
        """Test execution running state."""
        execution = Execution(
            id="exec-1",
            name="test-execution",
            workload_name="test-workload",
            cluster_name="test-cluster",
            status=ExecutionStatus.RUNNING,
        )
        
        assert execution.is_running is True
        assert execution.is_finished is False
    
    def test_execution_finished(self):
        """Test execution finished state."""
        execution = Execution(
            id="exec-1",
            name="test-execution",
            workload_name="test-workload",
            cluster_name="test-cluster",
            status=ExecutionStatus.COMPLETED,
        )
        
        assert execution.is_running is False
        assert execution.is_finished is True
    
    def test_execution_duration(self):
        """Test execution duration calculation."""
        start = datetime(2024, 1, 1, 10, 0, 0)
        end = datetime(2024, 1, 1, 10, 5, 30)
        
        execution = Execution(
            id="exec-1",
            name="test-execution",
            workload_name="test-workload",
            cluster_name="test-cluster",
            started_at=start,
            completed_at=end,
        )
        
        assert execution.duration_seconds == 330
    
    def test_execution_duration_no_start(self):
        """Test execution duration with no start time."""
        execution = Execution(
            id="exec-1",
            name="test-execution",
            workload_name="test-workload",
            cluster_name="test-cluster",
        )
        
        assert execution.duration_seconds == 0


class TestEventModels:
    """Tests for event models."""
    
    def test_event_creation(self):
        """Test creating an event."""
        event = Event(
            type=EventType.AGENT_HEARTBEAT,
            source="agent-1",
            target="manager",
        )
        
        assert event.type == EventType.AGENT_HEARTBEAT
        assert event.source == "agent-1"
        assert event.target == "manager"
        assert event.timestamp is not None
    
    def test_event_to_json(self):
        """Test event JSON serialization."""
        event = Event(
            type=EventType.AGENT_HEARTBEAT,
            source="agent-1",
            target="manager",
            payload={"status": "online"},
        )
        
        json_data = event.to_json()
        
        assert json_data["type"] == "agent.heartbeat"
        assert json_data["source"] == "agent-1"
        assert json_data["payload"]["status"] == "online"
    
    def test_event_from_json(self):
        """Test event JSON deserialization."""
        json_data = {
            "type": "agent.heartbeat",
            "timestamp": "2024-01-01T10:00:00",
            "source": "agent-1",
            "target": "manager",
            "payload": {"status": "online"},
        }
        
        event = Event.from_json(json_data)
        
        assert event.type == EventType.AGENT_HEARTBEAT
        assert event.source == "agent-1"
        assert event.payload["status"] == "online"
