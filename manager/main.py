"""Scale Testing Framework - Manager Application."""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from manager.config import get_settings, Settings
from manager.storage.data_store import DataStore
from manager.dependencies import set_data_store, set_redis_client, get_data_store, get_redis_client
from common.messaging.redis_client import RedisClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager."""
    settings = get_settings()
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    
    # Initialize data store
    data_store = DataStore(settings.data_path)
    set_data_store(data_store)
    logger.info(f"Data store initialized at {settings.data_path}")
    
    # Initialize Redis client
    redis_client = RedisClient(
        url=settings.redis_url,
        client_id="manager"
    )
    set_redis_client(redis_client)
    
    redis_connected = False
    try:
        await redis_client.connect()
        
        # Subscribe to agent messages
        await redis_client.subscribe(RedisClient.CHANNEL_MANAGER)
        await redis_client.subscribe_pattern(f"{RedisClient.CHANNEL_METRICS}:*")
        await redis_client.start_listening()
        
        redis_connected = True
        logger.info("Manager connected to Redis and started successfully")
        
    except Exception as e:
        logger.warning(f"Redis connection failed (manager will work in HTTP-only mode): {e}")
        redis_connected = False
    
    try:
        yield
    finally:
        # Cleanup
        if redis_connected:
            try:
                redis_client = get_redis_client()
                await redis_client.disconnect()
                logger.info("Manager disconnected from Redis")
            except Exception as e:
                logger.warning(f"Error disconnecting from Redis: {e}")
        logger.info("Manager shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Scale Testing Framework for Storage Products",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Register exception handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "error": str(exc)},
        )
    
    # Register routers
    from manager.api.routes import clusters, clients, workloads, executions, prechecks, metrics, system, network
    
    app.include_router(system.router, prefix="/api/v1/system", tags=["System"])
    app.include_router(clusters.router, prefix="/api/v1/clusters", tags=["Clusters"])
    app.include_router(clients.router, prefix="/api/v1/clients", tags=["Clients"])
    app.include_router(workloads.router, prefix="/api/v1/workloads", tags=["Workloads"])
    app.include_router(executions.router, prefix="/api/v1/executions", tags=["Executions"])
    app.include_router(prechecks.router, prefix="/api/v1/prechecks", tags=["Prechecks"])
    app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["Metrics"])
    app.include_router(network.router, prefix="/api/v1/network", tags=["Network"])
    
    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "status": "running",
        }
    
    # Health check endpoint
    @app.get("/health")
    async def health():
        return {"status": "healthy"}
    
    return app


# Create the app instance
app = create_app()


def main():
    """Entry point for running the manager."""
    settings = get_settings()
    
    # Configure logging level
    logging.getLogger().setLevel(settings.log_level.upper())
    
    logger.info(f"Starting manager on {settings.host}:{settings.port}")
    
    uvicorn.run(
        "manager.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
