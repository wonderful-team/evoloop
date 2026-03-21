"""
File-based Cache implementation for embedded mode.

Wraps the original FileCache to conform to Cache interface.
"""

import asyncio
import json
import logging
from typing import Any

from app.infrastructure.cache.abstract import (
    Cache,
    CacheLock,
    CachePipeline,
    PubSubBackend,
)
from app.utils.pubsub import in_memory_bus

logger = logging.getLogger(__name__)


class InMemoryPubSubAdapter(PubSubBackend):
    """Pub/Sub using the global in_memory_bus."""

    def __init__(self):
        self._subscriptions: dict[str, asyncio.Queue] = {}

    async def subscribe(self, *channels: str) -> None:
        for channel in channels:
            if channel not in self._subscriptions:
                self._subscriptions[channel] = await in_memory_bus.subscribe(channel)

    async def unsubscribe(self, *channels: str) -> None:
        for channel in channels:
            if channel in self._subscriptions:
                await in_memory_bus.unsubscribe(channel, self._subscriptions[channel])
                del self._subscriptions[channel]

    async def get_message(self, ignore_subscribe_messages: bool = False, timeout: float = None) -> dict | None:
        if not self._subscriptions:
            return None
        
        # Get first subscribed channel
        channel = next(iter(self._subscriptions.keys()))
        queue = self._subscriptions[channel]

        try:
            if timeout:
                msg = await asyncio.wait_for(queue.get(), timeout=timeout)
            else:
                msg = queue.get_nowait()
            return {"type": "message", "channel": channel, "data": msg}
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            return None

    async def close(self) -> None:
        for channel, queue in list(self._subscriptions.items()):
            await in_memory_bus.unsubscribe(channel, queue)
        self._subscriptions.clear()


class FileCacheLockAdapter(CacheLock):
    """No-op lock for file-based cache (embedded mode doesn't need distributed locks)."""

    def __init__(self, name: str):
        self.name = name
        self._locked = False

    async def acquire(self, blocking: bool = True, blocking_timeout: float = None) -> bool:
        self._locked = True
        return True

    async def release(self) -> None:
        self._locked = False


class FileCachePipelineAdapter(CachePipeline):
    """Pipeline for batching operations on FileCache."""

    def __init__(self, backend: "FileCache"):
        self._backend = backend
        self._commands: list[tuple[str, tuple, dict]] = []

    def get(self, key: str) -> "FileCachePipelineAdapter":
        self._commands.append(("get", (key,), {}))
        return self

    def set(self, key: str, value: Any, ex: int | None = None) -> "FileCachePipelineAdapter":
        self._commands.append(("set", (key, value), {"ex": ex}))
        return self

    def delete(self, *keys: str) -> "FileCachePipelineAdapter":
        self._commands.append(("delete", keys, {}))
        return self

    def hget(self, name: str, key: str) -> "FileCachePipelineAdapter":
        self._commands.append(("hget", (name, key), {}))
        return self

    def hset(self, name: str, key: str | None = None, value: Any = None, mapping: dict | None = None) -> "FileCachePipelineAdapter":
        self._commands.append(("hset", (name, key, value), {"mapping": mapping}))
        return self

    def hgetall(self, name: str) -> "FileCachePipelineAdapter":
        self._commands.append(("hgetall", (name,), {}))
        return self

    def hdel(self, name: str, *keys: str) -> "FileCachePipelineAdapter":
        self._commands.append(("hdel", (name,) + keys, {}))
        return self

    def sadd(self, name: str, *values: Any) -> "FileCachePipelineAdapter":
        self._commands.append(("sadd", (name,) + values, {}))
        return self

    def srem(self, name: str, *values: Any) -> "FileCachePipelineAdapter":
        self._commands.append(("srem", (name,) + values, {}))
        return self

    async def execute(self) -> list[Any]:
        results = []
        for method_name, args, kwargs in self._commands:
            method = getattr(self._backend, method_name)
            try:
                result = await method(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.debug(f"Pipeline command {method_name} failed: {e}")
                results.append(None)
        self._commands.clear()
        return results


class FileCache(Cache):
    """
    Embedded mode cache backend using file-based storage.
    
    Wraps the existing FileCache implementation.
    """

    def __init__(self):
        from app.infrastructure.cache.file_cache import get_file_cache
        self._cache = get_file_cache()

    # ========== Key-Value Operations ==========

    async def get(self, key: str) -> Any | None:
        return await self._cache.get(key)

    async def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        # FileCache set uses **kwargs, pass ttl as ex
        return await self._cache.set(key, value)

    async def setex(self, key: str, ex: int, value: Any) -> bool:
        return await self._cache.setex(key, ex, value)

    async def delete(self, key: str) -> int:
        # FileCache delete accepts *keys
        return await self._cache.delete(key)

    async def exists(self, key: str) -> bool:
        return await self._cache.exists(key)

    async def expire(self, key: str, seconds: int) -> bool:
        # FileCache doesn't support explicit expire, handled by TTL on set
        return True

    async def incr(self, key: str, amount: int = 1) -> int:
        return await self._cache.incr(key, amount)

    # ========== Hash Operations ==========

    async def hget(self, name: str, key: str) -> Any | None:
        return await self._cache.hget(name, key)

    async def hset(self, name: str, key: str | None = None, value: Any = None, mapping: dict | None = None) -> int:
        return await self._cache.hset(name, key=key, value=value, mapping=mapping)

    async def hgetall(self, name: str) -> dict:
        return await self._cache.hgetall(name)

    async def hdel(self, name: str, *keys: str) -> int:
        return await self._cache.hdel(name, *keys)

    # ========== Set Operations ==========

    async def sadd(self, name: str, *values: Any) -> int:
        return await self._cache.sadd(name, *values)

    async def srem(self, name: str, *values: Any) -> int:
        return await self._cache.srem(name, *values)

    async def smembers(self, name: str) -> set:
        return await self._cache.smembers(name)

    async def sismember(self, name: str, value: Any) -> bool:
        return await self._cache.sismember(name, value)

    # ========== List Operations ==========

    async def lpush(self, name: str, *values: Any) -> int:
        return await self._cache.lpush(name, *values)

    async def ltrim(self, name: str, start: int, end: int) -> bool:
        return await self._cache.ltrim(name, start, end)

    # ========== Pub/Sub ==========

    async def publish(self, channel: str, message: Any) -> int:
        await self._cache.publish(channel, message)
        return 1

    def pubsub(self) -> PubSubBackend:
        return InMemoryPubSubAdapter()

    # ========== Locks ==========

    def lock(self, name: str, timeout: float = None, blocking: bool = True, blocking_timeout: float = None) -> CacheLock:
        return FileCacheLockAdapter(name)

    # ========== Pipeline ==========

    def pipeline(self) -> CachePipeline:
        return FileCachePipelineAdapter(self)

    # ========== Lifecycle ==========

    async def close(self) -> None:
        await self._cache.aclose()
