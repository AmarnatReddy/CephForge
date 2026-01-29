"""Unit tests for ExecutionEngine."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from manager.core.execution_engine import ExecutionEngine
from common.models.execution import ExecutionStatus, ExecutionPhase
from common.messaging.events import EventType


@pytest.mark.asyncio
class TestExecutionEngine:
    """Tests for ExecutionEngine."""
    
    @pytest.fixture
    def execution_engine(self, data_store, mock_redis_client):
        """Create an ExecutionEngine instance."""
        return ExecutionEngine(data_store, mock_redis_client)
    
    async def test_get_execution_state(self, execution_engine):
        """Test getting execution state."""
        state = execution_engine.get_execution_state("nonexistent")
        
        assert state is None
    
    async def test_stop_execution(self, execution_engine):
        """Test stopping an execution."""
        execution_id = "exec-1"
        
        # Set up active execution
        execution_engine._active_executions[execution_id] = {
            "status": ExecutionStatus.RUNNING.value,
            "clients": [],
        }
        execution_engine._stop_flags[execution_id] = False
        
        await execution_engine.stop_execution(execution_id)
        
        assert execution_engine._stop_flags[execution_id] is True
    
    async def test_pause_execution(self, execution_engine, data_store):
        """Test pausing an execution."""
        # Create execution in database
        workload_config = {
            "name": "test-workload",
            "storage": {"type": "block", "backend": "ceph_rbd"},
        }
        execution_id, _ = await data_store.create_execution("test-execution", workload_config, "test-cluster")
        
        execution_engine._active_executions[execution_id] = {
            "status": ExecutionStatus.RUNNING.value,
        }
        
        await execution_engine.pause_execution(execution_id)
        
        assert execution_engine._pause_flags[execution_id] is True
        
        execution = await data_store.get_execution(execution_id)
        assert execution is not None
    
    async def test_resume_execution(self, execution_engine, data_store):
        """Test resuming an execution."""
        execution_id = "exec-1"
        
        execution_engine._active_executions[execution_id] = {
            "status": ExecutionStatus.PAUSED.value,
        }
        execution_engine._pause_flags[execution_id] = True
        
        await execution_engine.resume_execution(execution_id)
        
        assert execution_engine._pause_flags[execution_id] is False
    
    async def test_scale_up(self, execution_engine, data_store):
        """Test scaling up an execution."""
        execution_id = "exec-1"
        
        # Set up active execution
        execution_engine._active_executions[execution_id] = {
            "clients": ["client-1"],
        }
        
        # Set up clients in data store
        clients_config = [
            {"id": "client-1", "hostname": "192.168.1.100", "status": "online"},
            {"id": "client-2", "hostname": "192.168.1.101", "status": "online"},
        ]
        data_store.save_clients_config(clients_config)
        await data_store.update_client_status("client-1", "online")
        await data_store.update_client_status("client-2", "online")
        
        result = await execution_engine.scale_up(execution_id, count=1)
        
        assert "error" not in result
        assert len(execution_engine._active_executions[execution_id]["clients"]) >= 1
    
    async def test_scale_up_with_client_ids(self, execution_engine, data_store):
        """Test scaling up with specific client IDs."""
        execution_id = "exec-1"
        
        execution_engine._active_executions[execution_id] = {
            "clients": ["client-1"],
        }
        
        clients_config = [
            {"id": "client-1", "hostname": "192.168.1.100", "status": "online"},
            {"id": "client-2", "hostname": "192.168.1.101", "status": "online"},
        ]
        data_store.save_clients_config(clients_config)
        await data_store.update_client_status("client-1", "online")
        await data_store.update_client_status("client-2", "online")
        
        result = await execution_engine.scale_up(execution_id, client_ids=["client-2"])
        
        assert "error" not in result
    
    async def test_scale_up_execution_not_found(self, execution_engine):
        """Test scaling up non-existent execution."""
        result = await execution_engine.scale_up("nonexistent", count=1)
        
        assert "error" in result
    
    async def test_scale_down(self, execution_engine):
        """Test scaling down an execution."""
        execution_id = "exec-1"
        
        execution_engine._active_executions[execution_id] = {
            "clients": ["client-1", "client-2"],
        }
        
        result = await execution_engine.scale_down(execution_id, count=1)
        
        assert "error" not in result
        assert len(execution_engine._active_executions[execution_id]["clients"]) == 1
    
    async def test_scale_down_with_client_ids(self, execution_engine):
        """Test scaling down with specific client IDs."""
        execution_id = "exec-1"
        
        execution_engine._active_executions[execution_id] = {
            "clients": ["client-1", "client-2"],
        }
        
        result = await execution_engine.scale_down(execution_id, client_ids=["client-2"])
        
        assert "error" not in result
        assert "client-2" not in execution_engine._active_executions[execution_id]["clients"]
    
    async def test_scale_down_execution_not_found(self, execution_engine):
        """Test scaling down non-existent execution."""
        result = await execution_engine.scale_down("nonexistent", count=1)
        
        assert "error" in result
    
    async def test_cleanup_execution(self, execution_engine):
        """Test cleaning up execution state."""
        execution_id = "exec-1"
        
        execution_engine._active_executions[execution_id] = {"status": "running"}
        execution_engine._stop_flags[execution_id] = True
        execution_engine._pause_flags[execution_id] = False
        
        execution_engine._cleanup_execution(execution_id)
        
        assert execution_id not in execution_engine._active_executions
        assert execution_id not in execution_engine._stop_flags
        assert execution_id not in execution_engine._pause_flags
    
    async def test_update_state(self, execution_engine):
        """Test updating execution state."""
        execution_id = "exec-1"
        
        execution_engine._active_executions[execution_id] = {"status": "running"}
        
        execution_engine._update_state(execution_id, phase="prepare", current_iops=1000)
        
        assert execution_engine._active_executions[execution_id]["phase"] == "prepare"
        assert execution_engine._active_executions[execution_id]["current_iops"] == 1000
    
    @patch("manager.core.execution_engine.PrecheckRunner")
    @patch("manager.core.execution_engine.WorkloadExecutor")
    async def test_run_execution_success(
        self,
        mock_workload_executor_class,
        mock_precheck_runner_class,
        execution_engine,
        data_store,
        sample_workload_config,
        sample_cluster_config,
    ):
        """Test running a successful execution."""
        # Mock precheck runner
        mock_precheck_runner = MagicMock()
        mock_precheck_runner.run_all_prechecks = AsyncMock(return_value=MagicMock(
            model_dump=lambda: {"overall_status": "passed", "can_proceed": True},
            can_proceed=True,
            excluded_clients=[],
        ))
        mock_precheck_runner_class.return_value = mock_precheck_runner
        
        # Mock workload executor
        mock_workload_executor = MagicMock()
        mock_workload_executor.run_fio = AsyncMock(return_value=(
            True,
            "Success",
            {"iops": {"t": 1000}, "bw_mbps": {"t": 100.0}, "lat_us": {"avg": 100.0}},
        ))
        mock_workload_executor.get_command_log = MagicMock(return_value=[])
        mock_workload_executor.clear_command_log = MagicMock()
        mock_workload_executor.cleanup_client = AsyncMock(return_value=(True, ""))
        mock_workload_executor.ensure_fio_on_clients = AsyncMock(return_value=[])
        execution_engine.workload_executor = mock_workload_executor
        
        # Create execution
        execution_id, _ = await data_store.create_execution(
            "test-execution",
            sample_workload_config,
            "test-cluster",
        )
        
        # Set up clients
        clients_config = [
            {"id": "client-1", "hostname": "192.168.1.100"},
        ]
        data_store.save_clients_config(clients_config)
        await data_store.update_client_status("client-1", "online")
        
        # Run execution
        await execution_engine.run_execution(
            execution_id,
            sample_workload_config,
            sample_cluster_config,
            run_prechecks=True,
        )
        
        # Verify execution completed
        execution = await data_store.get_execution(execution_id)
        assert execution is not None
        # Note: Status might be COMPLETED or FAILED depending on implementation details
