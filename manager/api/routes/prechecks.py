"""Precheck endpoints."""

from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Body, BackgroundTasks
from pydantic import BaseModel

from manager.dependencies import get_data_store
from common.utils import generate_id

router = APIRouter()


class PrecheckRequest(BaseModel):
    """Request model for running prechecks."""
    cluster_name: str
    check_cluster: bool = True
    check_clients: bool = True
    check_network: bool = False
    custom_commands: list[dict] = []


class CommandRequest(BaseModel):
    """Request model for running a custom command."""
    command: str
    description: str = ""
    timeout: int = 60
    blocking: bool = False


@router.post("/run")
async def run_prechecks(request: PrecheckRequest):
    """Run all prechecks for a cluster."""
    store = get_data_store()
    
    # Validate cluster
    cluster = store.get_cluster(request.cluster_name)
    if not cluster:
        raise HTTPException(
            status_code=404,
            detail=f"Cluster '{request.cluster_name}' not found"
        )
    
    # Get clients
    clients = await store.get_clients()
    
    # Import precheck runner
    from manager.prechecks.runner import PrecheckRunner
    
    # Create runner with configuration
    runner = PrecheckRunner(
        cluster_config=cluster,
        clients=clients,
        check_cluster=request.check_cluster,
        check_clients=request.check_clients,
        check_network=request.check_network,
        custom_commands=request.custom_commands,
    )
    
    # Run prechecks
    precheck_id = generate_id("precheck")
    report = await runner.run_all_prechecks(precheck_id)
    
    return report.model_dump()


@router.get("/{precheck_id}")
async def get_precheck_report(precheck_id: str):
    """Get a precheck report by ID."""
    store = get_data_store()
    
    # Try to find the report
    # Precheck IDs follow the pattern: precheck_<execution_id> or standalone precheck_<id>
    execution_id = precheck_id.replace("precheck_", "")
    
    report = store.get_precheck_report(execution_id)
    if report:
        return report
    
    # Check if it's a standalone precheck (not tied to execution)
    raise HTTPException(
        status_code=404,
        detail=f"Precheck report '{precheck_id}' not found"
    )


@router.post("/commands")
async def run_custom_commands(commands: list[CommandRequest]):
    """Run custom commands on the cluster."""
    store = get_data_store()
    
    # Get first cluster for running commands
    clusters = store.get_clusters()
    if not clusters:
        raise HTTPException(
            status_code=400,
            detail="No clusters registered"
        )
    
    cluster = clusters[0]
    
    from manager.prechecks.cluster.custom_commands import CustomCommandRunner, CustomCommandConfig
    
    runner = CustomCommandRunner(
        ceph_conf=cluster.ceph.conf_path if cluster.ceph else "/etc/ceph/ceph.conf"
    )
    
    configs = [
        CustomCommandConfig(
            command=cmd.command,
            description=cmd.description,
            timeout=cmd.timeout,
            blocking=cmd.blocking,
        )
        for cmd in commands
    ]
    
    results = await runner.run_multiple(configs)
    
    return {
        "results": [r.model_dump() for r in results],
        "total": len(results),
        "successful": sum(1 for r in results if r.success),
        "failed": sum(1 for r in results if not r.success),
    }


@router.get("/commands/presets")
async def list_command_presets():
    """List available command presets."""
    from manager.prechecks.cluster.custom_commands import CustomCommandRunner
    
    presets = []
    for name, config in CustomCommandRunner.COMMON_CEPH_COMMANDS.items():
        presets.append({
            "name": name,
            "command": config.command,
            "description": config.description,
        })
    
    return {
        "presets": presets,
        "total": len(presets),
    }


@router.post("/commands/preset/{preset_name}")
async def run_preset_command(preset_name: str):
    """Run a preset command."""
    store = get_data_store()
    
    clusters = store.get_clusters()
    if not clusters:
        raise HTTPException(
            status_code=400,
            detail="No clusters registered"
        )
    
    cluster = clusters[0]
    
    from manager.prechecks.cluster.custom_commands import CustomCommandRunner
    
    runner = CustomCommandRunner(
        ceph_conf=cluster.ceph.conf_path if cluster.ceph else "/etc/ceph/ceph.conf"
    )
    
    if preset_name not in runner.COMMON_CEPH_COMMANDS:
        raise HTTPException(
            status_code=404,
            detail=f"Preset '{preset_name}' not found"
        )
    
    result = await runner.run_preset(preset_name)
    
    return result.model_dump()
