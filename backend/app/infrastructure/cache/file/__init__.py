"""
File-based Cache implementation for embedded mode.

Provides FileCache (the public Cache interface) and related adapters.
Uses JSON files stored in ~/.evoloop/cache/
"""

import logging
from typing import Any

from app.infrastructure.cache.abstract import (
    Cache,
    CacheLock,
    CachePipeline,
    PubSubBackend,
)
from app.infrastructure.cache.file._core import FileCacheCore
from app.infrastructure.cache.file._lock import FileCacheLockAdapter
from app.infrastructure.cache.file._pipeline import FileCachePipelineAdapter
from app.infrastructure.cache.file._pubsub import InMemoryPubSubAdapter

logger = logging.getLogger(__name__)


class FileCache(Cache):
    def __init__(self):
        self._cache = FileCacheCore()

    # ========== Key-Value ==========

    async def get(self, key: str) -> Any | None:
        return await self._cache.get(key)

    async def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        return await self._cache.set(key, value)

    async def setex(self, key: str, ex: int, value: Any) -> bool:
        return await self._cache.setex(key, ex, value)

    async def delete(self, key: str) -> int:
        return await self._cache.delete(key)

    async def exists(self, key: str) -> bool:
        return await self._cache.exists(key)

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def incr(self, key: str, amount: int = 1) -> int:
        return await self._cache.incr(key, amount)

    # ========== Hash ==========

    async def hget(self, name: str, key: str) -> Any | None:
        return await self._cache.hget(name, key)

    async def hset(self, name: str, key: str | None = None, value: Any = None, mapping: dict | None = None) -> int:
        return await self._cache.hset(name, key=key, value=value, mapping=mapping)

    async def hgetall(self, name: str) -> dict:
        return await self._cache.hgetall(name)

    async def hdel(self, name: str, *keys: str) -> int:
        return await self._cache.hdel(name, *keys)

    async def hlen(self, name: str) -> int:
        return await self._cache.hlen(name)

    # ========== Set ==========

    async def sadd(self, name: str, *values: Any) -> int:
        return await self._cache.sadd(name, *values)

    async def scard(self, name: str) -> int:
        return await self._cache.scard(name)

    async def srem(self, name: str, *values: Any) -> int:
        return await self._cache.srem(name, *values)

    async def smembers(self, name: str) -> set:
        return await self._cache.smembers(name)

    async def sismember(self, name: str, value: Any) -> bool:
        return await self._cache.sismember(name, value)

    # ========== List ==========

    async def lpush(self, name: str, *values: Any) -> int:
        return await self._cache.lpush(name, *values)

    async def ltrim(self, name: str, start: int, end: int) -> bool:
        return await self._cache.ltrim(name, start, end)

    async def lrange(self, name: str, start: int, end: int) -> list:
        return await self._cache.lrange(name, start, end)

    # ========== Pub/Sub ==========

    async def publish(self, channel: str, message: Any) -> int:
        await self._cache._core.publish(channel, message)
        return 1

    def pubsub(self) -> PubSubBackend:
        return InMemoryPubSubAdapter()

    # ========== Lock ==========

    def lock(self, name: str, timeout: float | None = None, blocking: bool = True, blocking_timeout: float | None = None) -> CacheLock:
        return FileCacheLockAdapter(name)

    # ========== Pipeline ==========

    def pipeline(self) -> CachePipeline:
        return FileCachePipelineAdapter(self._cache)

    async def keys(self, pattern: str = "*", **kwargs) -> list[str]:
        return await self._cache.keys(pattern)

    # ========== Lifecycle ==========

    async def close(self) -> None:
        pass
