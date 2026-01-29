"""Scale Testing Framework - Agent Application."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from agent.config import get_settings, AgentSettings
from agent.core.executor import WorkloadExecutor
from agent.core.reporter import MetricsReporter
from common.messaging.redis_client import RedisClient
from common.messaging.events import (
    Event, EventType,
    create_register_event,
    create_heartbeat_event,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Global instances
redis_client: RedisClient | None = None
executor: WorkloadExecutor | None = None
reporter: MetricsReporter | None = None
_heartbeat_task: asyncio.Task | None = None
_running = False


def get_executor() -> WorkloadExecutor:
    """Get the global executor instance."""
    if executor is None:
        raise RuntimeError("Executor not initialized")
    return executor


def get_reporter() -> MetricsReporter:
    """Get the global reporter instance."""
    if reporter is None:
        raise RuntimeError("Reporter not initialized")
    return reporter


async def heartbeat_loop(settings: AgentSettings) -> None:
    """Send periodic heartbeats to manager."""
    global _running
    
    while _running:
        try:
            event = create_heartbeat_event(
                agent_id=settings.agent_id,
                status="online" if executor and not executor.is_running else "busy",
                metrics={
                    "current_execution": executor.current_execution_id if executor else None,
                },
            )
            await redis_client.publish_to_manager(event)
            logger.debug("Heartbeat sent")
        except Exception as e:
            logger.error(f"Failed to send heartbeat: {e}")
        
        await asyncio.sleep(settings.heartbeat_interval)


async def handle_event(event: Event) -> None:
    """Handle incoming events from manager."""
    logger.info(f"Received event: {event.type.value}")
    
    if event.type == EventType.EXECUTION_PREPARE:
        await executor.prepare(
            execution_id=event.execution_id,
            config=event.payload.get("config", {}),
        )
    
    elif event.type == EventType.EXECUTION_START:
        asyncio.create_task(
            executor.start(
                execution_id=event.execution_id,
                config=event.payload.get("config", {}),
            )
        )
    
    elif event.type == EventType.EXECUTION_STOP:
        await executor.stop(event.execution_id)
    
    elif event.type == EventType.EXECUTION_PAUSE:
        await executor.pause(event.execution_id)
    
    elif event.type == EventType.EXECUTION_RESUME:
        await executor.resume(event.execution_id)
    
    elif event.type == EventType.PRECHECK_REQUEST:
        # Handle precheck request
        pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager."""
    global redis_client, executor, reporter, _heartbeat_task, _running
    
    settings = get_settings()
    logger.info(f"Starting agent: {settings.agent_id}")
    
    # Ensure work directory exists
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize Redis client (optional)
    redis_client = RedisClient(
        url=settings.redis_url,
        client_id=settings.agent_id,
    )
    redis_connected = False
    
    # Initialize executor and reporter
    executor = WorkloadExecutor(
        agent_id=settings.agent_id,
        work_dir=settings.work_dir,
    )
    
    reporter = MetricsReporter(
        agent_id=settings.agent_id,
        redis_client=redis_client,
    )
    
    try:
        # Try to connect to Redis (optional - agent works without it)
        try:
            await redis_client.connect()
            redis_connected = True
            
            # Subscribe to agent-specific channel
            await redis_client.subscribe(f"{RedisClient.CHANNEL_AGENTS}:{settings.agent_id}")
            await redis_client.subscribe(RedisClient.CHANNEL_BROADCAST)
            
            # Register event handlers
            redis_client.on_event(EventType.EXECUTION_PREPARE, handle_event)
            redis_client.on_event(EventType.EXECUTION_START, handle_event)
            redis_client.on_event(EventType.EXECUTION_STOP, handle_event)
            redis_client.on_event(EventType.EXECUTION_PAUSE, handle_event)
            redis_client.on_event(EventType.EXECUTION_RESUME, handle_event)
            
            # Start listening
            await redis_client.start_listening()
            
            # Register with manager
            register_event = create_register_event(
                agent_id=settings.agent_id,
                hostname=settings.hostname,
                version=__import__("agent").__version__,
                capabilities={
                    "workloads": ["fio", "iozone", "dd"],
                    "storage_types": ["block", "file", "object"],
                },
            )
            await redis_client.publish_to_manager(register_event)
            
            logger.info(f"Agent connected to Redis at {settings.redis_url}")
            
        except Exception as redis_error:
            logger.warning(f"Redis connection failed (agent will work in HTTP-only mode): {redis_error}")
            redis_connected = False
        
        # Start heartbeat (works via HTTP regardless of Redis)
        _running = True
        _heartbeat_task = asyncio.create_task(heartbeat_loop(settings))
        
        logger.info(f"Agent {settings.agent_id} started successfully (Redis: {'connected' if redis_connected else 'disconnected'})")
        
        yield
        
    except Exception as e:
        logger.error(f"Failed to start agent: {e}")
        raise
    finally:
        # Cleanup
        _running = False
        
        if _heartbeat_task:
            _heartbeat_task.cancel()
            try:
                await _heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if executor:
            await executor.cleanup()
        
        # Only disconnect Redis if it was connected
        if redis_connected and redis_client:
            try:
                await redis_client.disconnect()
            except Exception:
                pass  # Ignore disconnect errors
        
        logger.info("Agent shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    
    app = FastAPI(
        title="Scale Agent",
        version=__import__("agent").__version__,
        description="Scale Testing Framework Agent",
        lifespan=lifespan,
    )
    
    @app.get("/")
    async def root():
        return {
            "agent_id": settings.agent_id,
            "hostname": settings.hostname,
            "status": "running",
        }
    
    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "agent_id": settings.agent_id,
            "version": __import__("agent").__version__,
            "pid": os.getpid(),
            "hostname": settings.hostname,
            "ip": settings.ip_address,
            "current_execution": executor.current_execution_id if executor else None,
            "is_busy": executor.is_running if executor else False,
        }
    
    @app.get("/status")
    async def status():
        if not executor:
            return {"status": "not_ready"}
        
        return {
            "agent_id": settings.agent_id,
            "is_running": executor.is_running,
            "current_execution": executor.current_execution_id,
            "current_workload": executor.current_workload,
        }
    
    @app.post("/stop")
    async def stop_workload():
        if not executor or not executor.is_running:
            return {"message": "No workload running"}
        
        await executor.stop(executor.current_execution_id)
        return {"message": "Stop signal sent"}
    
    return app


# Create the app instance
app = create_app()


def main():
    """Entry point for running the agent."""
    settings = get_settings()
    
    # Configure logging level
    logging.getLogger().setLevel(settings.log_level.upper())
    
    logger.info(f"Starting agent {settings.agent_id} on {settings.host}:{settings.port}")
    
    uvicorn.run(
        "agent.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
