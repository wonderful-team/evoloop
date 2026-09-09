"""
Redis implementation of Cache interface.
"""

import asyncio
import json
import logging
from typing import Any

from app.core.config import settings
from app.infrastructure.cache.abstract import (
    Cache,
    CacheLock,
    CachePipeline,
    PubSubBackend,
)
from app.utils.async_utils import LoopBoundResource

logger = logging.getLogger(__name__)


class RedisPubSubAdapter(PubSubBackend):
    """Adapter for Redis pub/sub."""

    def __init__(self, redis_pubsub):
        self._pubsub = redis_pubsub

    async def subscribe(self, *channels: str) -> None:
        await self._pubsub.subscribe(*channels)

    async def unsubscribe(self, *channels: str) -> None:
        await self._pubsub.unsubscribe(*channels)

    async def get_message(self, ignore_subscribe_messages: bool = False, timeout: float = None) -> dict | None:
        return await self._pubsub.get_message(ignore_subscribe_messages=ignore_subscribe_messages, timeout=timeout)

    async def close(self) -> None:
        await self._pubsub.close()


class RedisLockAdapter(CacheLock):
    """Adapter for Redis lock."""

    def __init__(self, redis_lock):
        self._lock = redis_lock

    async def acquire(self, blocking: bool = True, blocking_timeout: float = None) -> bool:
        return await self._lock.acquire(blocking=blocking, blocking_timeout=blocking_timeout)

    async def release(self) -> None:
        await self._lock.release()


class RedisPipelineAdapter(CachePipeline):
    """Adapter for Redis pipeline."""

    def __init__(self, pipeline):
        self._pipeline = pipeline

    def get(self, key: str) -> "RedisPipelineAdapter":
        self._pipeline.get(key)
        return self

    def set(self, key: str, value: Any, ex: int | None = None) -> "RedisPipelineAdapter":
        self._pipeline.set(key, value, ex=ex)
        return self

    def delete(self, *keys: str) -> "RedisPipelineAdapter":
        self._pipeline.delete(*keys)
        return self

    def hget(self, name: str, key: str) -> "RedisPipelineAdapter":
        self._pipeline.hget(name, key)
        return self

    def hset(self, name: str, key: str | None = None, value: Any = None, mapping: dict | None = None) -> "RedisPipelineAdapter":
        self._pipeline.hset(name, key=key, value=value, mapping=mapping)
        return self

    def hgetall(self, name: str) -> "RedisPipelineAdapter":
        self._pipeline.hgetall(name)
        return self

    def hdel(self, name: str, *keys: str) -> "RedisPipelineAdapter":
        self._pipeline.hdel(name, *keys)
        return self

    def hlen(self, name: str) -> "RedisPipelineAdapter":
        self._pipeline.hlen(name)
        return self

    def sadd(self, name: str, *values: Any) -> "RedisPipelineAdapter":
        self._pipeline.sadd(name, *values)
        return self

    def scard(self, name: str) -> "RedisPipelineAdapter":
        self._pipeline.scard(name)
        return self

    def srem(self, name: str, *values: Any) -> "RedisPipelineAdapter":
        self._pipeline.srem(name, *values)
        return self

    def lpush(self, name: str, *values: Any) -> "RedisPipelineAdapter":
        self._pipeline.lpush(name, *values)
        return self

    def ltrim(self, name: str, start: int, end: int) -> "RedisPipelineAdapter":
        self._pipeline.ltrim(name, start, end)
        return self

    async def execute(self) -> list[Any]:
        return await self._pipeline.execute()


class RedisCache(Cache):
    """
    Production cache backend using Redis.
    """

    def __init__(self):
        async def cleanup_redis(client):
            await client.close()

        self._redis_pool = LoopBoundResource(
            factory=self._create_redis,
            cleanup=cleanup_redis
        )

    def _create_redis(self):
        import redis.asyncio as redis_lib

        pool = redis_lib.ConnectionPool.from_url(
            settings.REDIS_URL or "redis://localhost:6379/0",
            encoding="utf-8",
            decode_responses=True,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
        )
        client = redis_lib.Redis(connection_pool=pool)

        try:
            loop_id = id(asyncio.get_running_loop())
        except RuntimeError:
            loop_id = "none"

        logger.info(f"[RedisCache] Connected to Redis (loop={loop_id})")
        return client

    async def _ensure_connected(self):
        """Lazy connection to Redis (now handled by LoopBoundResource)."""
        pass

    @property
    def _redis(self):
        return self._redis_pool.get()

    # ========== Key-Value Operations ==========

    async def get(self, key: str) -> Any | None:
        await self._ensure_connected()
        value = await self._redis.get(key)
        if value is None:
            return None
        # Try JSON decode
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        await self._ensure_connected()
        if not isinstance(value, (str, bytes)):
            value = json.dumps(value)
        return await self._redis.set(key, value, ex=ex)

    async def setex(self, key: str, ex: int, value: Any) -> bool:
        await self._ensure_connected()
        if not isinstance(value, (str, bytes)):
            value = json.dumps(value)
        return await self._redis.setex(key, ex, value)

    async def delete(self, key: str) -> int:
        await self._ensure_connected()
        return await self._redis.delete(key)

    async def exists(self, key: str) -> bool:
        await self._ensure_connected()
        return await self._redis.exists(key) > 0

    async def keys(self, pattern: str = "*", **kwargs) -> list[str]:
        """Find all keys matching the given pattern."""
        await self._ensure_connected()
        return await self._redis.keys(pattern)

    async def expire(self, key: str, seconds: int) -> bool:
        await self._ensure_connected()
        return await self._redis.expire(key, seconds)

    async def incr(self, key: str, amount: int = 1) -> int:
        await self._ensure_connected()
        return await self._redis.incr(key, amount)

    # ========== Hash Operations ==========

    async def hget(self, name: str, key: str) -> Any | None:
        await self._ensure_connected()
        value = await self._redis.hget(name, key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def hset(self, name: str, key: str | None = None, value: Any = None, mapping: dict | None = None) -> int:
        await self._ensure_connected()
        # JSON encode values if needed
        if mapping is not None:
            mapping = {
                k: json.dumps(v)
                if not isinstance(v, (str, bytes, int, float))
                else str(v)
                for k, v in mapping.items()
            }
        elif value is not None and key is not None:
            if not isinstance(value, (str, bytes, int, float)):
                value = json.dumps(value)
        return await self._redis.hset(name, key=key, value=value, mapping=mapping)

    async def hgetall(self, name: str) -> dict:
        await self._ensure_connected()
        result = await self._redis.hgetall(name)
        # Try JSON decode values
        decoded = {}
        for k, v in result.items():
            try:
                decoded[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                decoded[k] = v
        return decoded

    async def hdel(self, name: str, *keys: str) -> int:
        await self._ensure_connected()
        return await self._redis.hdel(name, *keys)

    async def hlen(self, name: str) -> int:
        await self._ensure_connected()
        return await self._redis.hlen(name)

    # ========== Set Operations ==========

    async def sadd(self, name: str, *values: Any) -> int:
        await self._ensure_connected()
        return await self._redis.sadd(name, *values)

    async def scard(self, name: str) -> int:
        await self._ensure_connected()
        return await self._redis.scard(name)

    async def srem(self, name: str, *values: Any) -> int:
        await self._ensure_connected()
        return await self._redis.srem(name, *values)

    async def smembers(self, name: str) -> set:
        await self._ensure_connected()
        return await self._redis.smembers(name)

    async def sismember(self, name: str, value: Any) -> bool:
        await self._ensure_connected()
        return await self._redis.sismember(name, value)

    # ========== List Operations ==========

    async def lpush(self, name: str, *values: Any) -> int:
        await self._ensure_connected()
        return await self._redis.lpush(name, *values)

    async def ltrim(self, name: str, start: int, end: int) -> bool:
        await self._ensure_connected()
        return await self._redis.ltrim(name, start, end)

    async def lrange(self, name: str, start: int, end: int) -> list:
        """Get range of values from list."""
        await self._ensure_connected()
        result = await self._redis.lrange(name, start, end)
        # Try JSON decode values
        decoded = []
        for v in result:
            try:
                decoded.append(json.loads(v))
            except (json.JSONDecodeError, TypeError):
                decoded.append(v)
        return decoded

    # ========== Pub/Sub ==========

    async def publish(self, channel: str, message: Any) -> int:
        await self._ensure_connected()
        if not isinstance(message, (str, bytes)):
            message = json.dumps(message)
        return await self._redis.publish(channel, message)

    def pubsub(self) -> PubSubBackend:
        return RedisPubSubAdapter(self._redis.pubsub())

    # ========== Locks ==========

    def lock(self, name: str, timeout: float = None, blocking: bool = True, blocking_timeout: float = None) -> CacheLock:
        redis_lock = self._redis.lock(name, timeout=timeout, blocking=blocking, blocking_timeout=blocking_timeout)
        return RedisLockAdapter(redis_lock)

    # ========== Pipeline ==========

    def pipeline(self) -> CachePipeline:
        return RedisPipelineAdapter(self._redis.pipeline())

    # ========== Lifecycle ==========

    async def close(self) -> None:
        await self._redis_pool.flush_all()
