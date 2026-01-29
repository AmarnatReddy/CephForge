"""Redis client for pub/sub messaging."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Optional, Any, Dict, List
from datetime import datetime

import redis.asyncio as redis

from common.messaging.events import Event, EventType

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client for pub/sub messaging."""
    
    # Channel prefixes
    CHANNEL_AGENTS = "scale:agents"
    CHANNEL_MANAGER = "scale:manager"
    CHANNEL_METRICS = "scale:metrics"
    CHANNEL_BROADCAST = "scale:broadcast"
    
    def __init__(
        self,
        url: str = "redis://localhost:6379",
        client_id: str = "manager",
    ):
        self.url = url
        self.client_id = client_id
        self._redis: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._handlers: dict[str, list[Callable]] = {}
        self._running = False
        self._listener_task: Optional[asyncio.Task] = None
    
    async def connect(self) -> None:
        """Connect to Redis."""
        if self._redis is not None:
            return
        
        logger.info(f"Connecting to Redis at {self.url}")
        self._redis = redis.from_url(self.url, decode_responses=True)
        
        # Test connection
        await self._redis.ping()
        logger.info("Connected to Redis successfully")
    
    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        self._running = False
        
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
        
        if self._redis:
            await self._redis.close()
            self._redis = None
        
        logger.info("Disconnected from Redis")
    
    async def publish(self, channel: str, event: Event) -> int:
        """Publish an event to a channel."""
        if not self._redis:
            raise RuntimeError("Not connected to Redis")
        
        message = json.dumps(event.to_json())
        result = await self._redis.publish(channel, message)
        logger.debug(f"Published to {channel}: {event.type.value}")
        return result
    
    async def publish_to_agent(self, agent_id: str, event: Event) -> int:
        """Publish an event to a specific agent."""
        channel = f"{self.CHANNEL_AGENTS}:{agent_id}"
        return await self.publish(channel, event)
    
    async def publish_to_manager(self, event: Event) -> int:
        """Publish an event to the manager."""
        return await self.publish(self.CHANNEL_MANAGER, event)
    
    async def publish_broadcast(self, event: Event) -> int:
        """Publish an event to all agents."""
        return await self.publish(self.CHANNEL_BROADCAST, event)
    
    async def publish_metrics(self, execution_id: str, event: Event) -> int:
        """Publish metrics for an execution."""
        channel = f"{self.CHANNEL_METRICS}:{execution_id}"
        return await self.publish(channel, event)
    
    def on_event(self, event_type: EventType | str, handler: Callable) -> None:
        """Register a handler for an event type."""
        key = event_type.value if isinstance(event_type, EventType) else event_type
        if key not in self._handlers:
            self._handlers[key] = []
        self._handlers[key].append(handler)
        logger.debug(f"Registered handler for {key}")
    
    def on_any(self, handler: Callable) -> None:
        """Register a handler for all events."""
        self.on_event("*", handler)
    
    async def subscribe(self, *channels: str) -> None:
        """Subscribe to channels."""
        if not self._redis:
            raise RuntimeError("Not connected to Redis")
        
        if not self._pubsub:
            self._pubsub = self._redis.pubsub()
        
        await self._pubsub.subscribe(*channels)
        logger.info(f"Subscribed to channels: {channels}")
    
    async def subscribe_pattern(self, *patterns: str) -> None:
        """Subscribe to channel patterns."""
        if not self._redis:
            raise RuntimeError("Not connected to Redis")
        
        if not self._pubsub:
            self._pubsub = self._redis.pubsub()
        
        await self._pubsub.psubscribe(*patterns)
        logger.info(f"Subscribed to patterns: {patterns}")
    
    async def start_listening(self) -> None:
        """Start listening for messages in background."""
        if self._running:
            return
        
        self._running = True
        self._listener_task = asyncio.create_task(self._listen_loop())
        logger.info("Started message listener")
    
    async def _listen_loop(self) -> None:
        """Background loop to listen for messages."""
        if not self._pubsub:
            raise RuntimeError("Not subscribed to any channels")
        
        while self._running:
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0
                )
                
                if message is not None:
                    await self._handle_message(message)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in message listener: {e}")
                await asyncio.sleep(1)
    
    async def _handle_message(self, message: dict) -> None:
        """Handle an incoming message."""
        try:
            data = message.get("data")
            if not isinstance(data, str):
                return
            
            event_data = json.loads(data)
            event = Event.from_json(event_data)
            
            # Call handlers for this event type
            handlers = self._handlers.get(event.type.value, [])
            handlers.extend(self._handlers.get("*", []))
            
            for handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    logger.error(f"Handler error for {event.type.value}: {e}")
                    
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON message: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    # Convenience methods for common operations
    
    async def set(self, key: str, value: Any, ex: int = None) -> None:
        """Set a key-value pair."""
        if not self._redis:
            raise RuntimeError("Not connected to Redis")
        
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        await self._redis.set(key, value, ex=ex)
    
    async def get(self, key: str) -> Optional[str]:
        """Get a value by key."""
        if not self._redis:
            raise RuntimeError("Not connected to Redis")
        return await self._redis.get(key)
    
    async def delete(self, key: str) -> int:
        """Delete a key."""
        if not self._redis:
            raise RuntimeError("Not connected to Redis")
        return await self._redis.delete(key)
    
    async def hset(self, name: str, key: str, value: Any) -> int:
        """Set a hash field."""
        if not self._redis:
            raise RuntimeError("Not connected to Redis")
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        return await self._redis.hset(name, key, value)
    
    async def hget(self, name: str, key: str) -> Optional[str]:
        """Get a hash field."""
        if not self._redis:
            raise RuntimeError("Not connected to Redis")
        return await self._redis.hget(name, key)
    
    async def hgetall(self, name: str) -> dict:
        """Get all hash fields."""
        if not self._redis:
            raise RuntimeError("Not connected to Redis")
        return await self._redis.hgetall(name)
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set a key's time to live."""
        if not self._redis:
            raise RuntimeError("Not connected to Redis")
        return await self._redis.expire(key, seconds)
