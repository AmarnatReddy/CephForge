"""Unit tests for DataStore."""

import pytest
import json
import yaml
from datetime import datetime
from pathlib import Path

from manager.storage.data_store import DataStore
from common.models.cluster import ClusterConfig, StorageType, StorageBackend, CephConnection
from common.models.execution import ExecutionStatus


@pytest.mark.asyncio
class TestDataStore:
    """Tests for DataStore."""
    
    async def test_init(self, temp_dir):
        """Test DataStore initialization."""
        store = DataStore(temp_dir)
        
        assert store.base_path == temp_dir
        assert store.db_path == temp_dir / "scale.db"
        assert store.db_path.exists()
        
        # Check directories created
        assert (temp_dir / "config" / "clusters").exists()
        assert (temp_dir / "config" / "clients").exists()
        assert (temp_dir / "config" / "workloads" / "templates").exists()
        assert (temp_dir / "config" / "workloads" / "custom").exists()
        assert (temp_dir / "executions").exists()
        assert (temp_dir / "logs").exists()
    
    def test_get_clusters_empty(self, data_store):
        """Test getting clusters when none exist."""
        clusters = data_store.get_clusters()
        
        assert clusters == []
    
    def test_save_and_get_cluster(self, data_store):
        """Test saving and getting a cluster."""
        cluster = ClusterConfig(
            name="test-cluster",
            storage_type=StorageType.BLOCK,
            backend=StorageBackend.CEPH_RBD,
            ceph=CephConnection(monitors=["192.168.1.10:6789"]),
        )
        
        path = data_store.save_cluster(cluster)
        
        assert Path(path).exists()
        
        retrieved = data_store.get_cluster("test-cluster")
        
        assert retrieved is not None
        assert retrieved.name == "test-cluster"
        assert retrieved.storage_type == StorageType.BLOCK
    
    def test_get_cluster_nonexistent(self, data_store):
        """Test getting non-existent cluster."""
        cluster = data_store.get_cluster("nonexistent")
        
        assert cluster is None
    
    def test_delete_cluster(self, data_store):
        """Test deleting a cluster."""
        cluster = ClusterConfig(
            name="test-cluster",
            storage_type=StorageType.BLOCK,
            backend=StorageBackend.CEPH_RBD,
            ceph=CephConnection(monitors=["192.168.1.10:6789"]),
        )
        
        data_store.save_cluster(cluster)
        result = data_store.delete_cluster("test-cluster")
        
        assert result is True
        assert data_store.get_cluster("test-cluster") is None
    
    def test_save_clients_config(self, data_store):
        """Test saving client configurations."""
        clients = [
            {"id": "client-1", "hostname": "192.168.1.100"},
            {"id": "client-2", "hostname": "192.168.1.101"},
        ]
        
        data_store.save_clients_config(clients)
        
        clients_file = data_store.base_path / "config" / "clients" / "clients.yaml"
        assert clients_file.exists()
        
        with open(clients_file) as f:
            data = yaml.safe_load(f)
            assert len(data["clients"]) == 2
    
    def test_get_clients_config_empty(self, data_store):
        """Test getting clients config when file doesn't exist."""
        clients = data_store.get_clients_config()
        
        assert clients == []
    
    async def test_update_client_status(self, data_store):
        """Test updating client status."""
        await data_store.update_client_status(
            "client-1",
            "online",
            agent_version="1.0.0",
            hostname="192.168.1.100",
        )
        
        status = await data_store.get_client_status("client-1")
        
        assert status is not None
        assert status["status"] == "online"
        assert status["agent_version"] == "1.0.0"
    
    async def test_update_client_status_clear_error(self, data_store):
        """Test that error message is cleared when status is online."""
        await data_store.update_client_status(
            "client-1",
            "error",
            error_message="Some error",
        )
        
        await data_store.update_client_status(
            "client-1",
            "online",
        )
        
        status = await data_store.get_client_status("client-1")
        assert status["error_message"] == ""
    
    async def test_get_clients(self, data_store):
        """Test getting all clients."""
        # Save client config
        clients_config = [
            {"id": "client-1", "hostname": "192.168.1.100"},
        ]
        data_store.save_clients_config(clients_config)
        
        # Update status
        await data_store.update_client_status("client-1", "online")
        
        clients = await data_store.get_clients()
        
        assert len(clients) == 1
        assert clients[0]["id"] == "client-1"
        assert clients[0]["status"] == "online"
    
    def test_save_and_get_workload(self, data_store):
        """Test saving and getting a workload."""
        workload = {
            "name": "test-workload",
            "cluster_name": "test-cluster",
            "storage_type": "block",
        }
        
        path = data_store.save_workload("test-workload", workload)
        
        assert Path(path).exists()
        
        retrieved = data_store.get_workload("test-workload")
        
        assert retrieved is not None
        assert retrieved["name"] == "test-workload"
    
    def test_get_workload_templates(self, data_store):
        """Test getting workload templates."""
        workload = {
            "name": "template-1",
            "cluster_name": "test-cluster",
        }
        
        data_store.save_workload("template-1", workload, is_template=True)
        
        templates = data_store.get_workload_templates()
        
        assert len(templates) == 1
        assert templates[0]["name"] == "template-1"
        assert templates[0]["_is_template"] is True
    
    def test_delete_workload(self, data_store):
        """Test deleting a workload."""
        workload = {
            "name": "test-workload",
            "cluster_name": "test-cluster",
        }
        
        data_store.save_workload("test-workload", workload)
        result = data_store.delete_workload("test-workload")
        
        assert result is True
        assert data_store.get_workload("test-workload") is None
    
    async def test_create_execution(self, data_store):
        """Test creating an execution."""
        workload_config = {
            "name": "test-workload",
            "storage": {
                "type": "block",
                "backend": "ceph_rbd",
            },
        }
        
        execution_id, exec_dir = await data_store.create_execution(
            "test-execution",
            workload_config,
            "test-cluster",
        )
        
        assert execution_id.startswith("exec_")
        assert exec_dir.exists()
        assert (exec_dir / "config.yaml").exists()
        assert (exec_dir / "metrics").exists()
        
        # Check database record
        execution = await data_store.get_execution(execution_id)
        assert execution is not None
        assert execution["name"] == "test-execution"
        assert execution["status"] == "pending"
    
    async def test_update_execution_status(self, data_store):
        """Test updating execution status."""
        workload_config = {
            "name": "test-workload",
            "storage": {"type": "block", "backend": "ceph_rbd"},
        }
        
        execution_id, _ = await data_store.create_execution(
            "test-execution",
            workload_config,
            "test-cluster",
        )
        
        await data_store.update_execution_status(
            execution_id,
            ExecutionStatus.RUNNING.value,
            total_iops=1000,
        )
        
        execution = await data_store.get_execution(execution_id)
        assert execution["status"] == ExecutionStatus.RUNNING.value
        assert execution["total_iops"] == 1000
    
    async def test_update_execution_status_auto_timestamps(self, data_store):
        """Test that timestamps are set automatically."""
        workload_config = {
            "name": "test-workload",
            "storage": {"type": "block", "backend": "ceph_rbd"},
        }
        
        execution_id, _ = await data_store.create_execution(
            "test-execution",
            workload_config,
            "test-cluster",
        )
        
        await data_store.update_execution_status(
            execution_id,
            ExecutionStatus.RUNNING.value,
        )
        
        execution = await data_store.get_execution(execution_id)
        assert execution["started_at"] is not None
        
        await data_store.update_execution_status(
            execution_id,
            ExecutionStatus.COMPLETED.value,
        )
        
        execution = await data_store.get_execution(execution_id)
        assert execution["completed_at"] is not None
    
    async def test_get_executions(self, data_store):
        """Test getting recent executions."""
        workload_config = {
            "name": "test-workload",
            "storage": {"type": "block", "backend": "ceph_rbd"},
        }
        
        # Create multiple executions
        for i in range(3):
            await data_store.create_execution(
                f"test-execution-{i}",
                workload_config,
                "test-cluster",
            )
        
        executions = await data_store.get_executions(limit=10)
        
        assert len(executions) == 3
    
    def test_append_metrics(self, data_store):
        """Test appending metrics."""
        execution_id = "exec_test"
        exec_dir = data_store.base_path / "executions" / execution_id / "metrics"
        exec_dir.mkdir(parents=True)
        
        metrics = {
            "ts": datetime.utcnow().isoformat(),
            "iops": {"t": 1000},
        }
        
        data_store.append_metrics(execution_id, metrics)
        
        metrics_file = exec_dir / "aggregate.jsonl"
        assert metrics_file.exists()
        
        with open(metrics_file) as f:
            line = f.readline().strip()
            data = json.loads(line)
            assert data["iops"]["t"] == 1000
    
    def test_append_client_metrics(self, data_store):
        """Test appending client metrics."""
        execution_id = "exec_test"
        client_id = "client-1"
        exec_dir = data_store.base_path / "executions" / execution_id / "metrics" / "clients"
        exec_dir.mkdir(parents=True)
        
        metrics = {
            "ts": datetime.utcnow().isoformat(),
            "iops": {"t": 500},
        }
        
        data_store.append_client_metrics(execution_id, client_id, metrics)
        
        metrics_file = exec_dir / f"{client_id}.jsonl"
        assert metrics_file.exists()
    
    def test_read_metrics(self, data_store):
        """Test reading metrics."""
        execution_id = "exec_test"
        exec_dir = data_store.base_path / "executions" / execution_id / "metrics"
        exec_dir.mkdir(parents=True)
        
        metrics_file = exec_dir / "aggregate.jsonl"
        
        # Write some metrics
        with open(metrics_file, "w") as f:
            for i in range(3):
                metrics = {
                    "ts": datetime.utcnow().isoformat(),
                    "iops": {"t": 1000 + i},
                }
                f.write(json.dumps(metrics) + "\n")
        
        metrics = data_store.read_metrics(execution_id)
        
        assert len(metrics) == 3
        assert metrics[0]["iops"]["t"] == 1000
    
    def test_save_and_get_summary(self, data_store):
        """Test saving and getting execution summary."""
        execution_id = "exec_test"
        exec_dir = data_store.base_path / "executions" / execution_id
        exec_dir.mkdir(parents=True)
        
        summary = {
            "execution_id": execution_id,
            "peak_iops": 1000,
            "peak_throughput_mbps": 100.5,
        }
        
        data_store.save_summary(execution_id, summary)
        
        retrieved = data_store.get_summary(execution_id)
        
        assert retrieved is not None
        assert retrieved["peak_iops"] == 1000
    
    def test_save_precheck_report(self, data_store):
        """Test saving precheck report."""
        execution_id = "exec_test"
        exec_dir = data_store.base_path / "executions" / execution_id
        exec_dir.mkdir(parents=True)
        
        report = {
            "overall_status": "passed",
            "cluster": {"health": "ok"},
            "clients": {"online": 2, "total": 2},
        }
        
        data_store.save_precheck_report(execution_id, report)
        
        report_file = exec_dir / "precheck_report.json"
        assert report_file.exists()
        
        retrieved = data_store.get_precheck_report(execution_id)
        assert retrieved is not None
        assert retrieved["overall_status"] == "passed"
    
    def test_write_log(self, data_store):
        """Test writing to log file."""
        execution_id = "exec_test"
        
        data_store.write_log(execution_id, "Test log message")
        
        log_file = data_store.get_log_path(execution_id)
        assert log_file.exists()
        
        with open(log_file) as f:
            content = f.read()
            assert "Test log message" in content
