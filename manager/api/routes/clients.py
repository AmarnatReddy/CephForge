"""Client management endpoints."""

from __future__ import annotations

import asyncio
from typing import Optional, List, Dict
from fastapi import APIRouter, HTTPException, Body, BackgroundTasks
from pydantic import BaseModel

from common.models.client import Client, ClientStatus, SSHConfig
from manager.dependencies import get_data_store
from manager.deployment.agent_deployer import AgentDeployer, DeploymentStatus
from manager.core.workload_executor import WorkloadExecutor

router = APIRouter()


class ClientCreate(BaseModel):
    """Request model for creating a client."""
    id: str
    hostname: str
    ssh_user: str = "root"
    ssh_key_path: Optional[str] = None
    ssh_password: Optional[str] = None
    ssh_port: int = 22
    agent_port: int = 8080
    tags: dict[str, str] = {}


class ClientsCreate(BaseModel):
    """Request model for creating multiple clients."""
    clients: list[ClientCreate]
    defaults: Optional[dict] = None
    deploy_agent: bool = True  # Auto-deploy agent by default
    push_ceph_config: bool = True  # Auto-push Ceph config from cluster
    cluster_name: Optional[str] = None  # Cluster to get Ceph config from


@router.get("/")
async def list_clients():
    """List all registered clients with their current status."""
    store = get_data_store()
    clients = await store.get_clients()
    
    return {
        "clients": clients,
        "total": len(clients),
        "online": sum(1 for c in clients if c.get("status") == "online"),
        "offline": sum(1 for c in clients if c.get("status") != "online"),
    }


@router.post("/")
async def register_clients(request: ClientsCreate, background_tasks: BackgroundTasks):
    """Register one or more clients and optionally deploy agents and push Ceph config."""
    store = get_data_store()
    
    # Get existing clients
    existing = store.get_clients_config()
    existing_ids = {c.get("id") for c in existing}
    
    # Add new clients
    added = []
    added_clients = []
    skipped = []
    
    for client in request.clients:
        if client.id in existing_ids:
            skipped.append(client.id)
            continue
        
        client_dict = client.model_dump(exclude_none=True)
        existing.append(client_dict)
        added.append(client.id)
        added_clients.append(client_dict)
    
    # Save updated list
    store.save_clients_config(existing, request.defaults)
    
    # Get cluster config for Ceph config push
    cluster_config = None
    if request.push_ceph_config and request.cluster_name:
        cluster = store.get_cluster(request.cluster_name)
        if cluster:
            cluster_config = cluster.model_dump(mode='json')
    
    # Background task for deployment and config push
    async def setup_clients():
        # Step 1: Push Ceph config if cluster is specified
        if cluster_config and added_clients:
            executor = WorkloadExecutor()
            ceph_results = await executor.push_ceph_config_to_clients(added_clients, cluster_config)
            for client_id, success, message in ceph_results:
                if success:
                    import logging
                    logging.getLogger(__name__).info(f"Pushed Ceph config to {client_id}")
                else:
                    import logging
                    logging.getLogger(__name__).warning(f"Failed to push Ceph config to {client_id}: {message}")
        
        # Step 2: Deploy agents
        if request.deploy_agent and added_clients:
            deployer = AgentDeployer()
            results = await deployer.deploy_to_clients(added_clients)
            for result in results:
                status = "online" if result.status == DeploymentStatus.SUCCESS else "error"
                error_msg = result.message if result.status != DeploymentStatus.SUCCESS else None
                await store.update_client_status(
                    client_id=result.client_id,
                    status=status,
                    hostname=result.hostname,
                    error_message=error_msg,
                )
    
    # Run setup in background
    if added_clients:
        background_tasks.add_task(asyncio.create_task, setup_clients())
    
    deployment_results = [{"client_id": c["id"], "status": "setting_up"} for c in added_clients] if added_clients else []
    
    return {
        "message": f"Registered {len(added)} clients",
        "added": added,
        "skipped": skipped,
        "total": len(existing),
        "deployment": deployment_results if (request.deploy_agent or request.push_ceph_config) else None,
        "ceph_config": "pushing" if cluster_config else None,
    }


@router.get("/{client_id}")
async def get_client(client_id: str):
    """Get client details by ID."""
    store = get_data_store()
    clients = await store.get_clients()
    
    for client in clients:
        if client.get("id") == client_id:
            # Get additional status from DB
            status = await store.get_client_status(client_id)
            if status:
                client.update(status)
            return client
    
    raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")


class ClientUpdate(BaseModel):
    """Request model for updating a client."""
    hostname: Optional[str] = None
    ssh_user: Optional[str] = None
    ssh_password: Optional[str] = None
    ssh_key_path: Optional[str] = None
    ssh_port: Optional[int] = None
    agent_port: Optional[int] = None
    tags: Optional[dict] = None


@router.put("/{client_id}")
async def update_client(client_id: str, update: ClientUpdate):
    """Update a client's configuration."""
    store = get_data_store()
    
    clients = store.get_clients_config()
    client_found = False
    
    for i, client in enumerate(clients):
        if client.get("id") == client_id:
            client_found = True
            # Update only provided fields
            if update.hostname is not None:
                clients[i]["hostname"] = update.hostname
            if update.ssh_user is not None:
                clients[i]["ssh_user"] = update.ssh_user
            if update.ssh_password is not None:
                clients[i]["ssh_password"] = update.ssh_password
            if update.ssh_key_path is not None:
                clients[i]["ssh_key_path"] = update.ssh_key_path
            if update.ssh_port is not None:
                clients[i]["ssh_port"] = update.ssh_port
            if update.agent_port is not None:
                clients[i]["agent_port"] = update.agent_port
            if update.tags is not None:
                clients[i]["tags"] = update.tags
            break
    
    if not client_found:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")
    
    store.save_clients_config(clients)
    
    return {"message": f"Client '{client_id}' updated successfully"}


@router.delete("/{client_id}")
async def delete_client(client_id: str):
    """Remove a client."""
    store = get_data_store()
    
    clients = store.get_clients_config()
    original_count = len(clients)
    
    clients = [c for c in clients if c.get("id") != client_id]
    
    if len(clients) == original_count:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")
    
    store.save_clients_config(clients)
    
    return {"message": f"Client '{client_id}' removed successfully"}


@router.post("/{client_id}/health")
async def check_client_health(client_id: str):
    """Run health check on a specific client."""
    store = get_data_store()
    clients = await store.get_clients()
    
    client = None
    for c in clients:
        if c.get("id") == client_id:
            client = c
            break
    
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")
    
    # Import here to avoid circular imports
    from manager.prechecks.client.connectivity import ClientHealthChecker
    
    checker = ClientHealthChecker(
        ssh_user=client.get("ssh_user", "root"),
        ssh_key_path=client.get("ssh_key_path"),
        ssh_password=client.get("ssh_password"),
    )
    
    # Get cluster for storage endpoint
    clusters = store.get_clusters()
    storage_endpoint = ""
    mount_points = []
    
    if clusters:
        cluster = clusters[0]
        if cluster.ceph:
            storage_endpoint = cluster.ceph.monitors[0].split(":")[0]
    
    result = await checker.check_single_client(
        client_id=client_id,
        hostname=client.get("hostname"),
        storage_endpoint=storage_endpoint,
        mount_points=mount_points,
    )
    
    # Update status in DB
    error_msg = None
    if hasattr(result, 'message') and result.status != "online":
        error_msg = result.message
    await store.update_client_status(
        client_id=client_id,
        status=result.status.value,
        agent_version=result.agent_version,
        hostname=client.get("hostname"),
        error_message=error_msg if result.status.value != "online" else None,
    )
    
    return result.model_dump()


@router.post("/health/all")
async def check_all_clients_health():
    """Run health check on all clients."""
    store = get_data_store()
    clients = await store.get_clients()
    
    if not clients:
        return {
            "message": "No clients registered",
            "results": [],
            "summary": {"total": 0, "online": 0, "offline": 0},
        }
    
    from manager.prechecks.client.connectivity import ClientHealthChecker
    
    # Get first client's SSH config as default
    first_client = clients[0]
    checker = ClientHealthChecker(
        ssh_user=first_client.get("ssh_user", "root"),
        ssh_key_path=first_client.get("ssh_key_path"),
        ssh_password=first_client.get("ssh_password"),
    )
    
    # Get cluster for storage endpoint
    clusters = store.get_clusters()
    storage_endpoint = ""
    
    if clusters:
        cluster = clusters[0]
        if cluster.ceph:
            storage_endpoint = cluster.ceph.monitors[0].split(":")[0]
    
    # Check all clients
    client_list = [
        {"id": c.get("id"), "hostname": c.get("hostname")}
        for c in clients
    ]
    
    results = await checker.check_all_clients(
        clients=client_list,
        storage_endpoint=storage_endpoint,
        mount_points=[],
    )
    
    # Update status in DB
    for result in results:
        error_msg = result.message if result.status != DeploymentStatus.SUCCESS else None
        await store.update_client_status(
            client_id=result.client_id,
            status="online" if result.status == DeploymentStatus.SUCCESS else "error",
            agent_version=result.agent_version,
            hostname=result.hostname,
            error_message=error_msg,
        )
    
    summary = checker.generate_summary(results)
    
    return {
        "results": [r.model_dump() for r in results],
        "summary": summary,
    }


@router.post("/{client_id}/deploy")
async def deploy_agent_to_client(client_id: str):
    """Deploy agent to a specific client."""
    store = get_data_store()
    clients = store.get_clients_config()
    
    client = None
    for c in clients:
        if c.get("id") == client_id:
            client = c
            break
    
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")
    
    # Status callback to update deployment progress
    async def status_callback(cid: str, status, message: str):
        await store.update_deployment_status(cid, status.value, message)
    
    deployer = AgentDeployer()
    result = await deployer.deploy_agent(
        client_id=client_id,
        hostname=client.get("hostname"),
        ssh_user=client.get("ssh_user", "root"),
        ssh_password=client.get("ssh_password"),
        ssh_key_path=client.get("ssh_key_path"),
        ssh_port=client.get("ssh_port", 22),
        agent_port=client.get("agent_port", 8080),
        status_callback=status_callback,
    )
    
    # Update client status
    status = "online" if result.status == DeploymentStatus.SUCCESS else "error"
    error_msg = result.message if result.status != DeploymentStatus.SUCCESS else None
    await store.update_client_status(
        client_id=client_id,
        status=status,
        hostname=client.get("hostname"),
        error_message=error_msg,
    )
    
    return {
        "client_id": result.client_id,
        "hostname": result.hostname,
        "status": result.status.value,
        "message": result.message,
    }


@router.post("/deploy/all")
async def deploy_agent_to_all_clients():
    """Deploy agent to all registered clients."""
    store = get_data_store()
    clients = store.get_clients_config()
    
    if not clients:
        return {
            "message": "No clients registered",
            "results": [],
        }
    
    deployer = AgentDeployer()
    results = await deployer.deploy_to_clients(clients)
    
    # Update client statuses
    for result in results:
        status = "online" if result.status == DeploymentStatus.SUCCESS else "error"
        error_msg = result.message if result.status != DeploymentStatus.SUCCESS else None
        await store.update_client_status(
            client_id=result.client_id,
            status=status,
            hostname=result.hostname,
            error_message=error_msg,
        )
    
    success_count = sum(1 for r in results if r.status == DeploymentStatus.SUCCESS)
    
    return {
        "message": f"Deployed to {success_count}/{len(results)} clients",
        "results": [
            {
                "client_id": r.client_id,
                "hostname": r.hostname,
                "status": r.status.value,
                "message": r.message,
            }
            for r in results
        ],
    }


@router.post("/{client_id}/stop-agent")
async def stop_agent_on_client(client_id: str):
    """Stop the agent on a specific client."""
    store = get_data_store()
    clients = store.get_clients_config()
    
    client = None
    for c in clients:
        if c.get("id") == client_id:
            client = c
            break
    
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")
    
    deployer = AgentDeployer()
    success = await deployer.stop_agent(
        hostname=client.get("hostname"),
        ssh_user=client.get("ssh_user", "root"),
        ssh_password=client.get("ssh_password"),
        ssh_key_path=client.get("ssh_key_path"),
        ssh_port=client.get("ssh_port", 22),
    )
    
    # Update client status
    await store.update_client_status(
        client_id=client_id,
        status="offline",
        hostname=client.get("hostname"),
    )
    
    return {
        "client_id": client_id,
        "success": success,
        "message": "Agent stopped" if success else "Failed to stop agent",
    }


@router.post("/push-ceph-config/{cluster_name}")
async def push_ceph_config_to_all_clients(cluster_name: str):
    """Push Ceph config files from cluster to all registered clients."""
    store = get_data_store()
    
    # Get cluster
    cluster = store.get_cluster(cluster_name)
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster '{cluster_name}' not found")
    
    cluster_config = cluster.model_dump(mode='json')
    
    if not cluster_config.get("installer_node"):
        raise HTTPException(
            status_code=400,
            detail="Cluster has no installer node configured. Cannot fetch Ceph config."
        )
    
    # Get all clients
    clients = store.get_clients_config()
    if not clients:
        return {
            "message": "No clients registered",
            "results": [],
        }
    
    # Push config to all clients
    executor = WorkloadExecutor()
    results = await executor.push_ceph_config_to_clients(clients, cluster_config)
    
    success_count = sum(1 for _, success, _ in results if success)
    
    return {
        "message": f"Pushed Ceph config to {success_count}/{len(results)} clients",
        "cluster": cluster_name,
        "results": [
            {"client_id": client_id, "success": success, "message": message}
            for client_id, success, message in results
        ],
    }


@router.post("/{client_id}/push-ceph-config/{cluster_name}")
async def push_ceph_config_to_client(client_id: str, cluster_name: str):
    """Push Ceph config files from cluster to a specific client."""
    store = get_data_store()
    
    # Get cluster
    cluster = store.get_cluster(cluster_name)
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster '{cluster_name}' not found")
    
    cluster_config = cluster.model_dump(mode='json')
    
    if not cluster_config.get("installer_node"):
        raise HTTPException(
            status_code=400,
            detail="Cluster has no installer node configured. Cannot fetch Ceph config."
        )
    
    # Get client
    clients = store.get_clients_config()
    client = None
    for c in clients:
        if c.get("id") == client_id:
            client = c
            break
    
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")
    
    # Push config
    executor = WorkloadExecutor()
    success, message = await executor.push_ceph_config_to_client(client, cluster_config)
    
    return {
        "client_id": client_id,
        "cluster": cluster_name,
        "success": success,
        "message": message,
    }
