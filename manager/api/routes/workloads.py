"""Workload configuration endpoints."""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Body

from common.models.workload import WorkloadConfig
from manager.dependencies import get_data_store

router = APIRouter()


@router.get("/")
async def list_workloads():
    """List all workload configurations."""
    store = get_data_store()
    workloads = store.get_workloads()
    
    return {
        "workloads": workloads,
        "total": len(workloads),
        "templates": sum(1 for w in workloads if w.get("_is_template")),
        "custom": sum(1 for w in workloads if not w.get("_is_template")),
    }


@router.get("/templates")
async def list_templates():
    """List workload templates."""
    store = get_data_store()
    templates = store.get_workload_templates()
    
    return {
        "templates": templates,
        "total": len(templates),
    }


@router.post("/")
async def create_workload(workload: WorkloadConfig):
    """Create a new workload configuration."""
    store = get_data_store()
    
    # Check if workload already exists
    existing = store.get_workload(workload.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Workload '{workload.name}' already exists"
        )
    
    # Use mode='json' to serialize enums as strings
    path = store.save_workload(
        workload.name,
        workload.model_dump(exclude_none=True, mode='json'),
        is_template=False,
    )
    
    return {
        "message": "Workload created successfully",
        "name": workload.name,
        "path": path,
    }


@router.get("/{name}")
async def get_workload(name: str):
    """Get workload configuration by name."""
    store = get_data_store()
    workload = store.get_workload(name)
    
    if not workload:
        raise HTTPException(status_code=404, detail=f"Workload '{name}' not found")
    
    return workload


@router.put("/{name}")
async def update_workload(name: str, workload: WorkloadConfig):
    """Update a workload configuration."""
    store = get_data_store()
    
    existing = store.get_workload(name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Workload '{name}' not found")
    
    # If name changed, delete old
    if workload.name != name:
        store.delete_workload(name)
    
    # Use mode='json' to serialize enums as strings
    path = store.save_workload(
        workload.name,
        workload.model_dump(exclude_none=True, mode='json'),
        is_template=False,
    )
    
    return {
        "message": "Workload updated successfully",
        "name": workload.name,
        "path": path,
    }


@router.delete("/{name}")
async def delete_workload(name: str):
    """Delete a workload configuration."""
    store = get_data_store()
    
    if not store.delete_workload(name):
        raise HTTPException(status_code=404, detail=f"Workload '{name}' not found")
    
    return {"message": f"Workload '{name}' deleted successfully"}


@router.post("/validate")
async def validate_workload(workload: WorkloadConfig):
    """Validate a workload configuration without saving."""
    store = get_data_store()
    
    errors = []
    warnings = []
    
    # Check if cluster exists
    cluster = store.get_cluster(workload.cluster_name)
    if not cluster:
        errors.append(f"Cluster '{workload.cluster_name}' not found")
    
    # Validate read/write percentages
    if workload.io.read_percent + workload.io.write_percent != 100:
        warnings.append("Read + Write percent should equal 100")
    
    # Validate client selection
    if workload.clients.mode == "count" and workload.clients.count is None:
        errors.append("Client count required when mode is 'count'")
    
    if workload.clients.mode == "specific" and not workload.clients.client_ids:
        errors.append("Client IDs required when mode is 'specific'")
    
    # Check if clients exist
    if workload.clients.mode == "specific":
        clients = await store.get_clients()
        client_ids = {c.get("id") for c in clients}
        missing = [cid for cid in workload.clients.client_ids if cid not in client_ids]
        if missing:
            errors.append(f"Clients not found: {missing}")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


@router.post("/from-template/{template_name}")
async def create_from_template(
    template_name: str,
    name: str = Body(..., embed=True),
    overrides: dict = Body(default={}, embed=True),
):
    """Create a new workload from a template."""
    store = get_data_store()
    
    template = store.get_workload(template_name)
    if not template:
        raise HTTPException(
            status_code=404,
            detail=f"Template '{template_name}' not found"
        )
    
    # Check if name already exists
    existing = store.get_workload(name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Workload '{name}' already exists"
        )
    
    # Merge template with overrides
    workload_data = {**template, **overrides}
    workload_data["name"] = name
    workload_data.pop("_path", None)
    workload_data.pop("_is_template", None)
    
    path = store.save_workload(name, workload_data, is_template=False)
    
    return {
        "message": "Workload created from template",
        "name": name,
        "template": template_name,
        "path": path,
    }
