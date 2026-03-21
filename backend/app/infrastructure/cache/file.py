"""
File-based Cache implementation for embedded mode.

Provides both the low-level FileCache implementation and the Cache interface adapter.
Uses JSON files stored in ~/.evoloop/cache/

Structure:
    ~/.evoloop/cache/
        strings/{key}.json
        hashes/{name}.json
        sets/{name}.json
        lists/{name}.json
"""

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Optional

from app.infrastructure.cache.abstract import (
    Cache,
    CacheLock,
    CachePipeline,
    PubSubBackend,
)
from app.utils.pubsub import in_memory_bus

logger = logging.getLogger(__name__)


# ============================================================================
# Low-level FileCache Implementation
# ============================================================================

class _FileCacheCore:
    """
    Low-level file-based cache implementation.
    
    This is the core implementation that directly operates on JSON files.
    Use FileCache (below) for the standard Cache interface.
    """

    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir is None:
            cache_dir = os.path.expanduser("~/.evoloop/cache")
        self.cache_dir = Path(cache_dir)
        self._ensure_directories()

    def _ensure_directories(self):
        """Create cache directories if they don't exist."""
        for subdir in ["strings", "hashes", "sets", "lists"]:
            (self.cache_dir / subdir).mkdir(parents=True, exist_ok=True)

    def _get_path(self, category: str, name: str) -> Path:
        """Get file path for a cache entry."""
        # Sanitize filename
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        return self.cache_dir / category / f"{safe_name}.json"

    def _read(self, category: str, name: str) -> Any:
        """Read data from cache file."""
        path = self._get_path(category, name)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.debug(f"Cache read error for {category}/{name}: {e}")
            return None

    def _write(self, category: str, name: str, data: Any) -> bool:
        """Write data to cache file."""
        path = self._get_path(category, name)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except IOError as e:
            logger.debug(f"Cache write error for {category}/{name}: {e}")
            return False

    def _delete(self, category: str, name: str) -> bool:
        """Delete cache file."""
        path = self._get_path(category, name)
        try:
            if path.exists():
                path.unlink()
            return True
        except IOError as e:
            logger.debug(f"Cache delete error for {category}/{name}: {e}")
            return False

    # String operations
    async def get(self, key: str) -> Optional[Any]:
        """Get string value."""
        return self._read("strings", key)

    async def set(self, key: str, value: Any, **kwargs) -> bool:
        """Set string value."""
        return self._write("strings", key, value)

    async def setex(self, key: str, time: int, value: Any) -> bool:
        """Set string value with expiry (no-op for file cache, expiry ignored)."""
        return self._write("strings", key, value)

    async def delete(self, *keys: str) -> int:
        """Delete keys."""
        count = 0
        for category in ["strings", "hashes", "sets", "lists"]:
            for key in keys:
                if self._delete(category, key):
                    count += 1
        return count

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        for category in ["strings", "hashes", "sets", "lists"]:
            path = self._get_path(category, key)
            if path.exists():
                return True
        return False

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiry (no-op for file cache)."""
        return True

    async def incr(self, key: str, amount: int = 1) -> int:
        """Increment key value."""
        data = self._read("strings", key)
        try:
            current = int(data) if data is not None else 0
        except (ValueError, TypeError):
            current = 0
        new_value = current + amount
        self._write("strings", key, new_value)
        return new_value

    # Hash operations
    async def hget(self, name: str, key: str) -> Optional[Any]:
        """Get hash field."""
        data = self._read("hashes", name)
        if data and isinstance(data, dict):
            return data.get(key)
        return None

    async def hset(self, name: str, key: str | None = None, value: Any = None, mapping: dict | None = None) -> int:
        """Set hash field(s)."""
        data = self._read("hashes", name) or {}
        if not isinstance(data, dict):
            data = {}

        count = 0
        if key is not None and value is not None:
            data[key] = value
            count += 1
        if mapping:
            data.update(mapping)
            count += len(mapping)

        self._write("hashes", name, data)
        return count

    async def hgetall(self, name: str) -> dict:
        """Get all hash fields."""
        data = self._read("hashes", name)
        return data if isinstance(data, dict) else {}

    async def hdel(self, name: str, *keys: str) -> int:
        """Delete hash fields."""
        data = self._read("hashes", name)
        if not isinstance(data, dict):
            return 0

        count = 0
        for key in keys:
            if key in data:
                del data[key]
                count += 1

        if data:
            self._write("hashes", name, data)
        else:
            self._delete("hashes", name)
        return count

    # Set operations
    async def sadd(self, name: str, *values: Any) -> int:
        """Add members to set."""
        data = self._read("sets", name)
        if not isinstance(data, list):
            data = []

        count = 0
        for value in values:
            if value not in data:
                data.append(value)
                count += 1

        self._write("sets", name, data)
        return count

    async def srem(self, name: str, *values: Any) -> int:
        """Remove members from set."""
        data = self._read("sets", name)
        if not isinstance(data, list):
            return 0

        count = 0
        for value in values:
            if value in data:
                data.remove(value)
                count += 1

        if data:
            self._write("sets", name, data)
        else:
            self._delete("sets", name)
        return count

    async def smembers(self, name: str) -> set:
        """Get all members of set."""
        data = self._read("sets", name)
        return set(data) if isinstance(data, list) else set()

    async def sismember(self, name: str, value: Any) -> bool:
        """Check if value is member of set."""
        data = self._read("sets", name)
        if isinstance(data, list):
            return value in data
        return False

    # List operations
    async def lpush(self, name: str, *values: Any) -> int:
        """Push values to left of list."""
        data = self._read("lists", name)
        if not isinstance(data, list):
            data = []

        for value in reversed(values):
            data.insert(0, value)

        self._write("lists", name, data)
        return len(data)

    async def ltrim(self, name: str, start: int, end: int) -> bool:
        """Trim list to specified range."""
        data = self._read("lists", name)
        if not isinstance(data, list):
            return True

        if end < 0:
            end = len(data) + end + 1
        else:
            end = end + 1

        trimmed = data[start:end]

        if trimmed:
            self._write("lists", name, trimmed)
        else:
            self._delete("lists", name)
        return True

    # Pub/Sub
    async def publish(self, channel: str, message: Any) -> int:
        """Publish message to in-memory bus."""
        await in_memory_bus.publish(channel, message)
        return 1

    async def aclose(self) -> None:
        """Close cache (no-op for file cache)."""
        pass


# ============================================================================
# Cache Interface Adapters
# ============================================================================

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


# ============================================================================
# Public Cache Interface
# ============================================================================

class FileCacheCore:
    """
    Standalone file-based cache implementation.
    
    This is the core implementation that directly operates on JSON files.
    For use in embedded mode or testing. For the standard Cache interface,
    use FileCache class instead.
    """

    def __init__(self, cache_dir: str | None = None):
        self._core = _FileCacheCore(cache_dir=cache_dir)

    # Proxy all methods to the core implementation
    async def get(self, key: str) -> Any | None:
        return await self._core.get(key)

    async def set(self, key: str, value: Any, **kwargs) -> bool:
        return await self._core.set(key, value, **kwargs)

    async def setex(self, key: str, time: int, value: Any) -> bool:
        return await self._core.setex(key, time, value)

    async def delete(self, *keys: str) -> int:
        return await self._core.delete(*keys)

    async def exists(self, *keys: str) -> int:
        """Check if keys exist (Redis-compatible: returns int)."""
        count = 0
        for key in keys:
            if await self._core.exists(key):
                count += 1
        return count

    async def expire(self, key: str, seconds: int) -> bool:
        return await self._core.expire(key, seconds)

    async def incr(self, key: str, amount: int = 1) -> int:
        return await self._core.incr(key, amount)

    async def hget(self, name: str, key: str) -> Any | None:
        return await self._core.hget(name, key)

    async def hset(self, name: str, key: str | None = None, value: Any = None, mapping: dict | None = None) -> int:
        return await self._core.hset(name, key=key, value=value, mapping=mapping)

    async def hgetall(self, name: str) -> dict:
        return await self._core.hgetall(name)

    async def hdel(self, name: str, *keys: str) -> int:
        return await self._core.hdel(name, *keys)

    async def sadd(self, name: str, *values: Any) -> int:
        return await self._core.sadd(name, *values)

    async def srem(self, name: str, *values: Any) -> int:
        return await self._core.srem(name, *values)

    async def smembers(self, name: str) -> set:
        return await self._core.smembers(name)

    async def sismember(self, name: str, value: Any) -> bool:
        return await self._core.sismember(name, value)

    async def lpush(self, name: str, *values: Any) -> int:
        return await self._core.lpush(name, *values)

    async def ltrim(self, name: str, start: int, end: int) -> bool:
        return await self._core.ltrim(name, start, end)

    async def lrange(self, name: str, start: int, end: int) -> list:
        """Get range of values from list."""
        data = self._core._read("lists", name)
        if not isinstance(data, list):
            return []
        if end < 0:
            end = len(data) + end + 1
        else:
            end = end + 1
        return data[start:end]


class FileCache(Cache):
    """
    Embedded mode cache backend using file-based storage.
    
    Implements the Cache abstract interface for compatibility with RedisCache.
    All data is stored as JSON files in ~/.evoloop/cache/
    """

    def __init__(self):
        self._cache = _FileCacheCore()

    # ========== Key-Value Operations ==========

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
