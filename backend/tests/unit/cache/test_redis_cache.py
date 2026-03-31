"""
Tests for RedisCache implementation.

These tests mock the Redis client to avoid requiring a real Redis server.
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.infrastructure.cache.redis import (
    RedisCache,
    RedisPubSubAdapter,
    RedisLockAdapter,
    RedisPipelineAdapter,
)


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value='"test_value"')  # JSON encoded
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.exists = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.setex = AsyncMock(return_value=True)
    redis.incr = AsyncMock(return_value=42)
    redis.hget = AsyncMock(return_value='"hash_value"')  # JSON encoded
    redis.hset = AsyncMock(return_value=1)
    redis.hgetall = AsyncMock(return_value={"field1": "value1"})  # Already decoded
    redis.hdel = AsyncMock(return_value=1)
    redis.sadd = AsyncMock(return_value=2)
    redis.srem = AsyncMock(return_value=1)
    redis.smembers = AsyncMock(return_value={"member1", "member2"})  # Already decoded
    redis.sismember = AsyncMock(return_value=1)
    redis.lpush = AsyncMock(return_value=2)
    redis.ltrim = AsyncMock(return_value=True)
    redis.lrange = AsyncMock(return_value=["item1", "item2"])  # Already decoded
    redis.publish = AsyncMock(return_value=1)
    redis.close = AsyncMock()
    return redis


@pytest.fixture
async def redis_cache(mock_redis):
    """Create RedisCache instance with mock Redis."""
    cache = RedisCache.__new__(RedisCache)
    cache._redis = mock_redis
    yield cache


class TestRedisCacheBasics:
    """Test basic key-value operations."""

    @pytest.mark.asyncio
    async def test_get(self, redis_cache, mock_redis):
        """Test get operation returns decoded value."""
        result = await redis_cache.get("test_key")
        assert result == "test_value"
        mock_redis.get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_get_none(self, redis_cache, mock_redis):
        """Test get operation returns None for missing key."""
        mock_redis.get.return_value = None
        result = await redis_cache.get("missing_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set(self, redis_cache, mock_redis):
        """Test set operation - strings not JSON encoded."""
        result = await redis_cache.set("key", "value", ex=3600)
        assert result is True
        mock_redis.set.assert_called_once_with("key", "value", ex=3600)

    @pytest.mark.asyncio
    async def test_set_dict(self, redis_cache, mock_redis):
        """Test set operation serializes dict to JSON."""
        data = {"nested": "value"}
        await redis_cache.set("key", data)
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "key"
        assert json.loads(call_args[0][1]) == data

    @pytest.mark.asyncio
    async def test_delete(self, redis_cache, mock_redis):
        """Test delete operation."""
        result = await redis_cache.delete("key")
        assert result == 1
        mock_redis.delete.assert_called_once_with("key")

    @pytest.mark.asyncio
    async def test_exists(self, redis_cache, mock_redis):
        """Test exists operation returns bool."""
        result = await redis_cache.exists("key")
        assert result is True  # Converted from 1 to bool
        mock_redis.exists.assert_called_once_with("key")


class TestRedisCacheHash:
    """Test hash operations."""

    @pytest.mark.asyncio
    async def test_hget(self, redis_cache, mock_redis):
        """Test hash get returns decoded value."""
        result = await redis_cache.hget("hash_name", "field")
        assert result == "hash_value"
        mock_redis.hget.assert_called_once_with("hash_name", "field")

    @pytest.mark.asyncio
    async def test_hset(self, redis_cache, mock_redis):
        """Test hash set."""
        result = await redis_cache.hset("hash_name", "field", "value")
        assert result == 1
        mock_redis.hset.assert_called_once_with("hash_name", key="field", value="value", mapping=None)

    @pytest.mark.asyncio
    async def test_hset_mapping(self, redis_cache, mock_redis):
        """Test hash set with mapping."""
        mapping = {"a": "1", "b": "2"}
        await redis_cache.hset("hash_name", mapping=mapping)
        mock_redis.hset.assert_called_once_with("hash_name", key=None, value=None, mapping=mapping)

    @pytest.mark.asyncio
    async def test_hgetall(self, redis_cache, mock_redis):
        """Test hash getall returns decoded dict."""
        result = await redis_cache.hgetall("hash_name")
        assert result == {"field1": "value1"}


class TestRedisCacheSet:
    """Test set operations."""

    @pytest.mark.asyncio
    async def test_sadd(self, redis_cache, mock_redis):
        """Test set add."""
        result = await redis_cache.sadd("set_name", "a", "b")
        assert result == 2

    @pytest.mark.asyncio
    async def test_smembers(self, redis_cache, mock_redis):
        """Test set members returns decoded set."""
        result = await redis_cache.smembers("set_name")
        assert result == {"member1", "member2"}

    @pytest.mark.asyncio
    async def test_sismember(self, redis_cache, mock_redis):
        """Test set ismember returns Redis result (1 for member)."""
        result = await redis_cache.sismember("set_name", "member")
        assert result == 1  # Redis returns 1 for member, 0 for non-member


class TestRedisCacheList:
    """Test list operations."""

    @pytest.mark.asyncio
    async def test_lpush(self, redis_cache, mock_redis):
        """Test list push."""
        result = await redis_cache.lpush("list_name", "a", "b")
        assert result == 2

    @pytest.mark.asyncio
    async def test_lrange(self, redis_cache, mock_redis):
        """Test list range - not implemented in RedisCache."""
        # lrange is not part of Cache interface
        assert not hasattr(redis_cache, 'lrange')

    @pytest.mark.asyncio
    async def test_ltrim(self, redis_cache, mock_redis):
        """Test list trim."""
        result = await redis_cache.ltrim("list_name", 0, 9)
        assert result is True


class TestRedisCachePubSub:
    """Test pub/sub operations."""

    @pytest.mark.asyncio
    async def test_publish(self, redis_cache, mock_redis):
        """Test publish."""
        result = await redis_cache.publish("channel", "message")
        assert result == 1

    def test_pubsub(self, redis_cache, mock_redis):
        """Test pubsub returns adapter."""
        mock_pubsub = MagicMock()
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
        result = redis_cache.pubsub()
        assert isinstance(result, RedisPubSubAdapter)


class TestRedisCachePipeline:
    """Test pipeline operations."""

    def test_pipeline(self, redis_cache, mock_redis):
        """Test pipeline returns adapter."""
        mock_pipe = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        result = redis_cache.pipeline()
        assert isinstance(result, RedisPipelineAdapter)


class TestRedisCacheLock:
    """Test lock operations."""

    def test_lock(self, redis_cache, mock_redis):
        """Test lock returns adapter."""
        mock_lock = MagicMock()
        mock_redis.lock = MagicMock(return_value=mock_lock)
        result = redis_cache.lock("lock_name", timeout=10)
        assert isinstance(result, RedisLockAdapter)


class TestRedisPubSubAdapter:
    """Test RedisPubSubAdapter."""

    @pytest.mark.asyncio
    async def test_subscribe(self):
        """Test subscribe delegates to underlying pubsub."""
        mock_pubsub = AsyncMock()
        adapter = RedisPubSubAdapter(mock_pubsub)
        await adapter.subscribe("channel1", "channel2")
        mock_pubsub.subscribe.assert_called_once_with("channel1", "channel2")

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """Test unsubscribe delegates to underlying pubsub."""
        mock_pubsub = AsyncMock()
        adapter = RedisPubSubAdapter(mock_pubsub)
        await adapter.unsubscribe("channel1")
        mock_pubsub.unsubscribe.assert_called_once_with("channel1")

    @pytest.mark.asyncio
    async def test_get_message(self):
        """Test get_message delegates to underlying pubsub."""
        mock_pubsub = AsyncMock()
        mock_pubsub.get_message.return_value = {"type": "message", "data": "test"}
        adapter = RedisPubSubAdapter(mock_pubsub)
        result = await adapter.get_message(ignore_subscribe_messages=True, timeout=5.0)
        assert result == {"type": "message", "data": "test"}


class TestRedisLockAdapter:
    """Test RedisLockAdapter."""

    @pytest.mark.asyncio
    async def test_acquire(self):
        """Test acquire delegates to underlying lock."""
        mock_lock = AsyncMock()
        mock_lock.acquire.return_value = True
        adapter = RedisLockAdapter(mock_lock)
        result = await adapter.acquire(blocking=True, blocking_timeout=10)
        assert result is True
        mock_lock.acquire.assert_called_once_with(blocking=True, blocking_timeout=10)

    @pytest.mark.asyncio
    async def test_release(self):
        """Test release delegates to underlying lock."""
        mock_lock = AsyncMock()
        adapter = RedisLockAdapter(mock_lock)
        await adapter.release()
        mock_lock.release.assert_called_once()


class TestRedisPipelineAdapter:
    """Test RedisPipelineAdapter."""

    def test_method_chaining(self):
        """Test pipeline methods return self for chaining."""
        mock_pipe = MagicMock()
        adapter = RedisPipelineAdapter(mock_pipe)
        
        # All methods should return self
        assert adapter.get("key") is adapter
        assert adapter.set("key", "value") is adapter
        assert adapter.delete("key") is adapter
        assert adapter.hget("name", "key") is adapter
        assert adapter.hset("name", "key", "value") is adapter
        assert adapter.hgetall("name") is adapter
        assert adapter.hdel("name", "key") is adapter
        assert adapter.sadd("name", "value") is adapter
        assert adapter.srem("name", "value") is adapter

    @pytest.mark.asyncio
    async def test_execute(self):
        """Test execute delegates to underlying pipeline."""
        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [1, 2, 3]
        adapter = RedisPipelineAdapter(mock_pipe)
        result = await adapter.execute()
        assert result == [1, 2, 3]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
