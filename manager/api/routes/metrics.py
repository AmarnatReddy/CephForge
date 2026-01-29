"""Metrics and reporting endpoints."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from manager.dependencies import get_data_store

router = APIRouter()


@router.get("/{execution_id}")
async def get_metrics(
    execution_id: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = Query(default=1000, le=10000),
):
    """Get historical metrics for an execution."""
    store = get_data_store()
    
    # Verify execution exists
    execution = await store.get_execution(execution_id)
    if not execution:
        raise HTTPException(
            status_code=404,
            detail=f"Execution '{execution_id}' not found"
        )
    
    # Read metrics
    metrics = store.read_metrics(
        execution_id,
        start_time=start_time,
        end_time=end_time,
    )
    
    # Apply limit
    if len(metrics) > limit:
        # Sample evenly
        step = len(metrics) // limit
        metrics = metrics[::step][:limit]
    
    return {
        "execution_id": execution_id,
        "metrics": metrics,
        "total": len(metrics),
        "start_time": start_time.isoformat() if start_time else None,
        "end_time": end_time.isoformat() if end_time else None,
    }


@router.get("/{execution_id}/latest")
async def get_latest_metrics(execution_id: str, count: int = Query(default=60, le=300)):
    """Get the latest N metrics samples."""
    store = get_data_store()
    
    execution = await store.get_execution(execution_id)
    if not execution:
        raise HTTPException(
            status_code=404,
            detail=f"Execution '{execution_id}' not found"
        )
    
    metrics = store.read_metrics(execution_id)
    
    # Get latest N
    latest = metrics[-count:] if len(metrics) > count else metrics
    
    return {
        "execution_id": execution_id,
        "metrics": latest,
        "count": len(latest),
    }


@router.get("/{execution_id}/aggregate")
async def get_aggregate_metrics(execution_id: str):
    """Get aggregated metrics for an entire execution."""
    store = get_data_store()
    
    execution = await store.get_execution(execution_id)
    if not execution:
        raise HTTPException(
            status_code=404,
            detail=f"Execution '{execution_id}' not found"
        )
    
    metrics = store.read_metrics(execution_id)
    
    if not metrics:
        return {
            "execution_id": execution_id,
            "message": "No metrics available",
        }
    
    # Calculate aggregates
    total_iops_read = 0
    total_iops_write = 0
    total_bw_read = 0
    total_bw_write = 0
    latencies = []
    
    for m in metrics:
        iops = m.get("iops", {})
        total_iops_read += iops.get("r", 0)
        total_iops_write += iops.get("w", 0)
        
        bw = m.get("bw_mbps", {})
        total_bw_read += bw.get("r", 0)
        total_bw_write += bw.get("w", 0)
        
        lat = m.get("lat_us", {})
        if lat.get("avg"):
            latencies.append(lat.get("avg"))
    
    count = len(metrics)
    
    return {
        "execution_id": execution_id,
        "samples": count,
        "iops": {
            "avg_read": total_iops_read / count if count > 0 else 0,
            "avg_write": total_iops_write / count if count > 0 else 0,
            "avg_total": (total_iops_read + total_iops_write) / count if count > 0 else 0,
        },
        "throughput_mbps": {
            "avg_read": total_bw_read / count if count > 0 else 0,
            "avg_write": total_bw_write / count if count > 0 else 0,
            "avg_total": (total_bw_read + total_bw_write) / count if count > 0 else 0,
        },
        "latency_us": {
            "avg": sum(latencies) / len(latencies) if latencies else 0,
            "min": min(latencies) if latencies else 0,
            "max": max(latencies) if latencies else 0,
        },
    }


@router.get("/export/{execution_id}")
async def export_metrics(
    execution_id: str,
    format: str = Query(default="json", enum=["json", "csv"]),
):
    """Export metrics for an execution."""
    store = get_data_store()
    
    execution = await store.get_execution(execution_id)
    if not execution:
        raise HTTPException(
            status_code=404,
            detail=f"Execution '{execution_id}' not found"
        )
    
    metrics = store.read_metrics(execution_id)
    
    if format == "json":
        content = json.dumps(metrics, indent=2)
        media_type = "application/json"
        filename = f"{execution_id}_metrics.json"
    else:  # csv
        # Convert to CSV
        if not metrics:
            content = "timestamp,iops_read,iops_write,bw_read_mbps,bw_write_mbps,latency_avg_us\n"
        else:
            lines = ["timestamp,iops_read,iops_write,bw_read_mbps,bw_write_mbps,latency_avg_us"]
            for m in metrics:
                iops = m.get("iops", {})
                bw = m.get("bw_mbps", {})
                lat = m.get("lat_us", {})
                lines.append(
                    f"{m.get('ts', '')},{iops.get('r', 0)},{iops.get('w', 0)},"
                    f"{bw.get('r', 0)},{bw.get('w', 0)},{lat.get('avg', 0)}"
                )
            content = "\n".join(lines)
        media_type = "text/csv"
        filename = f"{execution_id}_metrics.csv"
    
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.websocket("/live/{execution_id}")
async def live_metrics(websocket: WebSocket, execution_id: str):
    """WebSocket endpoint for live metrics streaming."""
    await websocket.accept()
    
    store = get_data_store()
    
    # Verify execution exists
    execution = await store.get_execution(execution_id)
    if not execution:
        await websocket.send_json({"error": f"Execution '{execution_id}' not found"})
        await websocket.close()
        return
    
    try:
        # Subscribe to metrics for this execution
        from manager.dependencies import get_redis_client
        redis = get_redis_client()
        
        # Create a simple polling loop for now
        # In production, you'd use Redis pub/sub properly
        last_count = 0
        
        while True:
            # Check if execution is still running
            execution = await store.get_execution(execution_id)
            if execution.get("status") not in ["running", "paused", "prechecks", "preparing"]:
                await websocket.send_json({
                    "event": "execution_complete",
                    "status": execution.get("status"),
                })
                break
            
            # Get latest metrics
            metrics = store.read_metrics(execution_id)
            
            if len(metrics) > last_count:
                # Send new metrics
                new_metrics = metrics[last_count:]
                for m in new_metrics:
                    await websocket.send_json({
                        "event": "metrics",
                        "data": m,
                    })
                last_count = len(metrics)
            
            # Also send current execution state
            await websocket.send_json({
                "event": "status",
                "data": {
                    "status": execution.get("status"),
                    "progress": execution.get("progress_percent", 0),
                    "clients": execution.get("client_count", 0),
                },
            })
            
            # Wait before next poll
            import asyncio
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"error": str(e)})
    finally:
        await websocket.close()
