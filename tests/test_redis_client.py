"""Unit tests for Redis client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from common.messaging.redis_client import RedisClient
from common.messaging.events import Event, EventType, create_heartbeat_event


@pytest.mark.asyncio
class TestRedisClient:
    """Tests for Redis client."""
    
    async def test_connect(self):
        """Test connecting to Redis."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_from_url.return_value = mock_redis
            
            client = RedisClient(url="redis://localhost:6379")
            await client.connect()
            
            assert client._redis is not None
            mock_redis.ping.assert_called_once()
    
    async def test_disconnect(self):
        """Test disconnecting from Redis."""
        client = RedisClient()
        client._redis = AsyncMock()
        client._pubsub = AsyncMock()
        client._listener_task = None
        client._running = False
        
        await client.disconnect()
        
        assert client._redis is None
        assert client._pubsub is None
    
    async def test_publish(self):
        """Test publishing an event."""
        client = RedisClient()
        client._redis = AsyncMock()
        client._redis.publish = AsyncMock(return_value=1)
        
        event = create_heartbeat_event("agent-1", "online")
        result = await client.publish("test:channel", event)
        
        assert result == 1
        client._redis.publish.assert_called_once()
    
    async def test_publish_not_connected(self):
        """Test publishing when not connected."""
        client = RedisClient()
        
        event = create_heartbeat_event("agent-1", "online")
        
        with pytest.raises(RuntimeError, match="Not connected"):
            await client.publish("test:channel", event)
    
    async def test_publish_to_agent(self):
        """Test publishing to specific agent."""
        client = RedisClient()
        client._redis = AsyncMock()
        client._redis.publish = AsyncMock(return_value=1)
        
        event = create_heartbeat_event("agent-1", "online")
        result = await client.publish_to_agent("agent-1", event)
        
        assert result == 1
        call_args = client._redis.publish.call_args
        assert call_args[0][0] == "scale:agents:agent-1"
    
    async def test_publish_to_manager(self):
        """Test publishing to manager."""
        client = RedisClient()
        client._redis = AsyncMock()
        client._redis.publish = AsyncMock(return_value=1)
        
        event = create_heartbeat_event("agent-1", "online")
        result = await client.publish_to_manager(event)
        
        assert result == 1
        call_args = client._redis.publish.call_args
        assert call_args[0][0] == RedisClient.CHANNEL_MANAGER
    
    async def test_publish_broadcast(self):
        """Test broadcasting to all agents."""
        client = RedisClient()
        client._redis = AsyncMock()
        client._redis.publish = AsyncMock(return_value=1)
        
        event = create_heartbeat_event("agent-1", "online")
        result = await client.publish_broadcast(event)
        
        assert result == 1
        call_args = client._redis.publish.call_args
        assert call_args[0][0] == RedisClient.CHANNEL_BROADCAST
    
    async def test_subscribe(self):
        """Test subscribing to channels."""
        client = RedisClient()
        client._redis = AsyncMock()
        client._redis.pubsub = MagicMock()
        mock_pubsub = AsyncMock()
        client._redis.pubsub.return_value = mock_pubsub
        mock_pubsub.subscribe = AsyncMock()
        
        await client.subscribe("channel1", "channel2")
        
        assert client._pubsub is not None
        mock_pubsub.subscribe.assert_called_once_with("channel1", "channel2")
    
    async def test_subscribe_pattern(self):
        """Test subscribing to channel patterns."""
        client = RedisClient()
        client._redis = AsyncMock()
        client._redis.pubsub = MagicMock()
        mock_pubsub = AsyncMock()
        client._redis.pubsub.return_value = mock_pubsub
        mock_pubsub.psubscribe = AsyncMock()
        
        await client.subscribe_pattern("scale:*")
        
        assert client._pubsub is not None
        mock_pubsub.psubscribe.assert_called_once_with("scale:*")
    
    async def test_on_event(self):
        """Test registering event handlers."""
        client = RedisClient()
        
        def handler(event):
            pass
        
        client.on_event(EventType.AGENT_HEARTBEAT, handler)
        
        assert EventType.AGENT_HEARTBEAT.value in client._handlers
        assert handler in client._handlers[EventType.AGENT_HEARTBEAT.value]
    
    async def test_on_any(self):
        """Test registering handler for all events."""
        client = RedisClient()
        
        def handler(event):
            pass
        
        client.on_any(handler)
        
        assert "*" in client._handlers
        assert handler in client._handlers["*"]
    
    async def test_set_get(self):
        """Test setting and getting values."""
        client = RedisClient()
        client._redis = AsyncMock()
        client._redis.set = AsyncMock()
        client._redis.get = AsyncMock(return_value="test_value")
        
        await client.set("test_key", "test_value")
        value = await client.get("test_key")
        
        assert value == "test_value"
        client._redis.set.assert_called_once()
        client._redis.get.assert_called_once()
    
    async def test_set_dict(self):
        """Test setting dictionary value."""
        import json
        
        client = RedisClient()
        client._redis = AsyncMock()
        client._redis.set = AsyncMock()
        
        test_dict = {"key": "value"}
        await client.set("test_key", test_dict)
        
        call_args = client._redis.set.call_args
        assert call_args[0][0] == "test_key"
        assert json.loads(call_args[0][1]) == test_dict
    
    async def test_delete(self):
        """Test deleting a key."""
        client = RedisClient()
        client._redis = AsyncMock()
        client._redis.delete = AsyncMock(return_value=1)
        
        result = await client.delete("test_key")
        
        assert result == 1
        client._redis.delete.assert_called_once_with("test_key")
    
    async def test_hset_hget(self):
        """Test hash set and get."""
        client = RedisClient()
        client._redis = AsyncMock()
        client._redis.hset = AsyncMock(return_value=1)
        client._redis.hget = AsyncMock(return_value="hash_value")
        
        await client.hset("hash_name", "field", "hash_value")
        value = await client.hget("hash_name", "field")
        
        assert value == "hash_value"
        client._redis.hset.assert_called_once()
        client._redis.hget.assert_called_once()
    
    async def test_hgetall(self):
        """Test getting all hash fields."""
        client = RedisClient()
        client._redis = AsyncMock()
        client._redis.hgetall = AsyncMock(return_value={"field1": "value1", "field2": "value2"})
        
        result = await client.hgetall("hash_name")
        
        assert result == {"field1": "value1", "field2": "value2"}
    
    async def test_expire(self):
        """Test setting key expiration."""
        client = RedisClient()
        client._redis = AsyncMock()
        client._redis.expire = AsyncMock(return_value=True)
        
        result = await client.expire("test_key", 60)
        
        assert result is True
        client._redis.expire.assert_called_once_with("test_key", 60)
