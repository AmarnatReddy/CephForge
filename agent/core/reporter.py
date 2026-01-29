"""Metrics reporter for sending metrics to manager."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from common.models.metrics import Metrics
from common.messaging.redis_client import RedisClient
from common.messaging.events import create_metrics_event

logger = logging.getLogger(__name__)


class MetricsReporter:
    """Report metrics to the manager."""
    
    def __init__(
        self,
        agent_id: str,
        redis_client: RedisClient,
        interval: float = 1.0,
    ):
        self.agent_id = agent_id
        self.redis_client = redis_client
        self.interval = interval
        
        self._is_running = False
        self._current_execution_id: Optional[str] = None
        self._report_task: Optional[asyncio.Task] = None
        self._latest_metrics: Optional[Metrics] = None
    
    def set_metrics(self, metrics: Metrics) -> None:
        """Update the latest metrics."""
        self._latest_metrics = metrics
    
    async def start_reporting(self, execution_id: str) -> None:
        """Start periodic metrics reporting."""
        if self._is_running:
            return
        
        self._is_running = True
        self._current_execution_id = execution_id
        self._report_task = asyncio.create_task(self._report_loop())
        logger.info(f"Started metrics reporting for execution: {execution_id}")
    
    async def stop_reporting(self) -> None:
        """Stop metrics reporting."""
        self._is_running = False
        
        if self._report_task:
            self._report_task.cancel()
            try:
                await self._report_task
            except asyncio.CancelledError:
                pass
            self._report_task = None
        
        self._current_execution_id = None
        self._latest_metrics = None
        logger.info("Stopped metrics reporting")
    
    async def _report_loop(self) -> None:
        """Periodic metrics reporting loop."""
        while self._is_running:
            try:
                if self._latest_metrics:
                    await self.report_metrics(self._latest_metrics)
                
                await asyncio.sleep(self.interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics report loop: {e}")
                await asyncio.sleep(self.interval)
    
    async def report_metrics(self, metrics: Metrics) -> None:
        """Send metrics to manager."""
        if not self._current_execution_id:
            return
        
        try:
            event = create_metrics_event(
                agent_id=self.agent_id,
                execution_id=self._current_execution_id,
                metrics=metrics.to_jsonl(),
            )
            
            await self.redis_client.publish_metrics(
                self._current_execution_id,
                event,
            )
            
            logger.debug(
                f"Reported metrics: IOPS={metrics.iops.total}, "
                f"BW={metrics.throughput.total_mbps:.2f}MB/s"
            )
            
        except Exception as e:
            logger.error(f"Failed to report metrics: {e}")
    
    async def report_final_metrics(self, metrics: Metrics) -> None:
        """Send final metrics summary."""
        await self.report_metrics(metrics)
        logger.info(f"Reported final metrics for execution: {self._current_execution_id}")
