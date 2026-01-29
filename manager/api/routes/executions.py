"""Test execution endpoints."""

from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Body, BackgroundTasks
from pydantic import BaseModel

from common.models.execution import ExecutionStatus
from manager.dependencies import get_data_store, get_redis_client
from manager.core.execution_engine import ExecutionEngine

router = APIRouter()

# Global execution engine instance
_execution_engine: ExecutionEngine | None = None


def get_execution_engine() -> ExecutionEngine:
    """Get or create the execution engine."""
    global _execution_engine
    if _execution_engine is None:
        _execution_engine = ExecutionEngine(
            data_store=get_data_store(),
            redis_client=get_redis_client(),
        )
    return _execution_engine


class ExecutionCreate(BaseModel):
    """Request model for creating an execution."""
    workload_name: str
    name: Optional[str] = None
    run_prechecks: bool = True


class ScaleRequest(BaseModel):
    """Request model for scaling clients."""
    action: str  # "add" or "remove"
    count: Optional[int] = None
    client_ids: Optional[list[str]] = None


@router.get("/")
async def list_executions(limit: int = 50):
    """List recent executions."""
    store = get_data_store()
    executions = await store.get_executions(limit=limit)
    
    return {
        "executions": executions,
        "total": len(executions),
    }


@router.post("/")
async def create_execution(
    request: ExecutionCreate,
    background_tasks: BackgroundTasks,
):
    """Start a new test execution."""
    store = get_data_store()
    
    # Load workload config
    workload = store.get_workload(request.workload_name)
    if not workload:
        raise HTTPException(
            status_code=404,
            detail=f"Workload '{request.workload_name}' not found"
        )
    
    # Validate cluster exists
    cluster = store.get_cluster(workload.get("cluster_name", ""))
    if not cluster:
        raise HTTPException(
            status_code=400,
            detail=f"Cluster '{workload.get('cluster_name')}' not found"
        )
    
    # Create execution with network baseline if available
    execution_name = request.name or f"{request.workload_name}_run"
    network_baseline = workload.get("network_baseline")
    
    execution_id, exec_dir = await store.create_execution(
        name=execution_name,
        workload_config=workload,
        cluster_name=workload.get("cluster_name", ""),
        network_baseline=network_baseline,
    )
    
    # Start execution in background
    engine = get_execution_engine()
    background_tasks.add_task(
        engine.run_execution,
        execution_id=execution_id,
        workload_config=workload,
        cluster_config=cluster.model_dump(),
        run_prechecks=request.run_prechecks,
    )
    
    return {
        "message": "Execution started",
        "execution_id": execution_id,
        "name": execution_name,
        "workload": request.workload_name,
        "status": ExecutionStatus.PENDING.value,
    }


@router.get("/{execution_id}")
async def get_execution(execution_id: str):
    """Get execution status and details."""
    store = get_data_store()
    execution = await store.get_execution(execution_id)
    
    if not execution:
        raise HTTPException(
            status_code=404,
            detail=f"Execution '{execution_id}' not found"
        )
    
    # Get current state from engine if running
    engine = get_execution_engine()
    if execution.get("status") == ExecutionStatus.RUNNING.value:
        current_state = engine.get_execution_state(execution_id)
        if current_state:
            execution.update(current_state)
    
    return execution


@router.post("/{execution_id}/stop")
async def stop_execution(execution_id: str):
    """Stop a running execution."""
    store = get_data_store()
    execution = await store.get_execution(execution_id)
    
    if not execution:
        raise HTTPException(
            status_code=404,
            detail=f"Execution '{execution_id}' not found"
        )
    
    if execution.get("status") not in [
        ExecutionStatus.RUNNING.value,
        ExecutionStatus.PAUSED.value,
        ExecutionStatus.PRECHECKS.value,
        ExecutionStatus.PREPARING.value,
    ]:
        raise HTTPException(
            status_code=400,
            detail=f"Execution is not running (status: {execution.get('status')})"
        )
    
    engine = get_execution_engine()
    await engine.stop_execution(execution_id)
    
    return {
        "message": "Stop signal sent",
        "execution_id": execution_id,
    }


@router.post("/{execution_id}/pause")
async def pause_execution(execution_id: str):
    """Pause a running execution."""
    store = get_data_store()
    execution = await store.get_execution(execution_id)
    
    if not execution:
        raise HTTPException(
            status_code=404,
            detail=f"Execution '{execution_id}' not found"
        )
    
    if execution.get("status") != ExecutionStatus.RUNNING.value:
        raise HTTPException(
            status_code=400,
            detail="Execution is not running"
        )
    
    engine = get_execution_engine()
    await engine.pause_execution(execution_id)
    
    return {
        "message": "Pause signal sent",
        "execution_id": execution_id,
    }


@router.post("/{execution_id}/resume")
async def resume_execution(execution_id: str):
    """Resume a paused execution."""
    store = get_data_store()
    execution = await store.get_execution(execution_id)
    
    if not execution:
        raise HTTPException(
            status_code=404,
            detail=f"Execution '{execution_id}' not found"
        )
    
    if execution.get("status") != ExecutionStatus.PAUSED.value:
        raise HTTPException(
            status_code=400,
            detail="Execution is not paused"
        )
    
    engine = get_execution_engine()
    await engine.resume_execution(execution_id)
    
    return {
        "message": "Resume signal sent",
        "execution_id": execution_id,
    }


@router.post("/{execution_id}/scale")
async def scale_execution(execution_id: str, request: ScaleRequest):
    """Scale clients during execution."""
    store = get_data_store()
    execution = await store.get_execution(execution_id)
    
    if not execution:
        raise HTTPException(
            status_code=404,
            detail=f"Execution '{execution_id}' not found"
        )
    
    if execution.get("status") != ExecutionStatus.RUNNING.value:
        raise HTTPException(
            status_code=400,
            detail="Can only scale running executions"
        )
    
    engine = get_execution_engine()
    
    if request.action == "add":
        result = await engine.scale_up(
            execution_id,
            count=request.count,
            client_ids=request.client_ids,
        )
    elif request.action == "remove":
        result = await engine.scale_down(
            execution_id,
            count=request.count,
            client_ids=request.client_ids,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action: {request.action}"
        )
    
    return result


@router.get("/{execution_id}/summary")
async def get_execution_summary(execution_id: str):
    """Get execution summary."""
    store = get_data_store()
    
    summary = store.get_summary(execution_id)
    if not summary:
        raise HTTPException(
            status_code=404,
            detail=f"Summary not found for execution '{execution_id}'"
        )
    
    return summary


@router.get("/{execution_id}/commands")
async def get_execution_commands(execution_id: str):
    """Get executed commands log for an execution."""
    store = get_data_store()
    
    # Check execution exists
    execution = await store.get_execution(execution_id)
    if not execution:
        raise HTTPException(
            status_code=404,
            detail=f"Execution '{execution_id}' not found"
        )
    
    commands = store.get_command_log(execution_id)
    
    return {
        "execution_id": execution_id,
        "commands": commands,
        "total": len(commands),
    }
