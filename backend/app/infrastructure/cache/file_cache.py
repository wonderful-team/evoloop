"""File-based cache for embedded mode.

Replaces Redis with a simple file-based implementation for embedded mode.
Uses JSON files stored in ~/.evoloop/cache/
"""

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Optional

from app.utils.pubsub import in_memory_bus

logger = logging.getLogger(__name__)


class FileCache:
    """File-based cache implementation for embedded mode.

    Mimics Redis API but stores data in JSON files.
    Structure:
        ~/.evoloop/cache/
            strings/{key}.json
            hashes/{name}.json
            sets/{name}.json
            lists/{name}.json
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

    async def exists(self, *keys: str) -> int:
        """Check if keys exist."""
        count = 0
        for category in ["strings", "hashes", "sets", "lists"]:
            for key in keys:
                path = self._get_path(category, key)
                if path.exists():
                    count += 1
        return count

    async def expire(self, key: str, time: int) -> bool:
        """Set expiry (no-op for file cache)."""
        return True

    async def ttl(self, key: str) -> int:
        """Get TTL (always returns -1 for no expiry)."""
        return -1

    async def keys(self, pattern: str = "*") -> list:
        """Get all keys matching pattern (simplified, no glob support)."""
        keys = []
        for category in ["strings", "hashes", "sets", "lists"]:
            dir_path = self.cache_dir / category
            if dir_path.exists():
                for f in dir_path.glob("*.json"):
                    key = f.stem
                    if pattern == "*" or pattern in key:
                        keys.append(f"{category}:{key}")
        return keys

    async def scan(self, cursor: int = 0, match: str = None, count: int = None):
        """Scan keys (simplified)."""
        all_keys = await self.keys(match or "*")
        return (0, all_keys)  # Always return cursor 0 (complete)

    # Hash operations
    async def hget(self, name: str, key: str) -> Optional[Any]:
        """Get hash field."""
        data = self._read("hashes", name)
        if data and isinstance(data, dict):
            return data.get(key)
        return None

    async def hset(self, name: str, key: str = None, value: Any = None, mapping: dict = None) -> int:
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

    async def hlen(self, name: str) -> int:
        """Get number of fields in hash."""
        data = self._read("hashes", name)
        return len(data) if isinstance(data, dict) else 0

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

    async def scard(self, name: str) -> int:
        """Get number of members in set."""
        data = self._read("sets", name)
        return len(data) if isinstance(data, list) else 0

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

    async def rpush(self, name: str, *values: Any) -> int:
        """Push values to right of list."""
        data = self._read("lists", name)
        if not isinstance(data, list):
            data = []

        data.extend(values)
        self._write("lists", name, data)
        return len(data)

    async def lpop(self, name: str, count: int = None) -> Any:
        """Pop value(s) from left of list."""
        data = self._read("lists", name)
        if not isinstance(data, list) or not data:
            return None

        if count is None:
            value = data.pop(0)
            if data:
                self._write("lists", name, data)
            else:
                self._delete("lists", name)
            return value
        else:
            values = data[:count]
            data = data[count:]
            if data:
                self._write("lists", name, data)
            else:
                self._delete("lists", name)
            return values

    async def rpop(self, name: str, count: int = None) -> Any:
        """Pop value(s) from right of list."""
        data = self._read("lists", name)
        if not isinstance(data, list) or not data:
            return None

        if count is None:
            value = data.pop()
            if data:
                self._write("lists", name, data)
            else:
                self._delete("lists", name)
            return value
        else:
            values = data[-count:]
            data = data[:-count]
            if data:
                self._write("lists", name, data)
            else:
                self._delete("lists", name)
            return values

    async def lrange(self, name: str, start: int, end: int) -> list:
        """Get range of values from list."""
        data = self._read("lists", name)
        if not isinstance(data, list):
            return []

        if end < 0:
            end = len(data) + end + 1
        else:
            end = end + 1

        return data[start:end]

    async def llen(self, name: str) -> int:
        """Get length of list."""
        data = self._read("lists", name)
        return len(data) if isinstance(data, list) else 0

    # Pub/Sub - use in-memory bus for real-time events
    async def publish(self, channel: str, message: Any) -> int:
        """Publish message to in-memory bus."""
        await in_memory_bus.publish(channel, message)
        return 1

    def pubsub(self, **kwargs):
        """Get pub/sub client using in-memory bus."""
        return InMemoryPubSub()

    async def aclose(self) -> None:
        """Close cache (no-op for file cache)."""
        pass

    # Pipeline support for compatibility with Redis
    def pipeline(self):
        """Return a pipeline object for batch operations."""
        return FileCachePipeline(self)

    # Utility
    async def clear(self) -> bool:
        """Clear all cache."""
        try:
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
            self._ensure_directories()
            return True
        except IOError as e:
            logger.error(f"Failed to clear cache: {e}")
            return False


class FileCachePipeline:
    """Pipeline for batching Redis-like operations on FileCache.

    Accumulates commands and executes them sequentially when execute() is called.
    This mimics Redis pipeline behavior for compatibility.
    """

    def __init__(self, cache: FileCache):
        self._cache = cache
        self._commands: list[tuple[str, tuple, dict]] = []

    def sadd(self, name: str, *values: Any) -> 'FileCachePipeline':
        """Queue a sadd operation."""
        self._commands.append(('sadd', (name, *values), {}))
        return self

    def srem(self, name: str, *values: Any) -> 'FileCachePipeline':
        """Queue a srem operation."""
        self._commands.append(('srem', (name, *values), {}))
        return self

    def hset(self, name: str, key: str = None, value: Any = None, mapping: dict = None) -> 'FileCachePipeline':
        """Queue an hset operation."""
        self._commands.append(('hset', (name, key, value), {'mapping': mapping}))
        return self

    def hdel(self, name: str, *keys: str) -> 'FileCachePipeline':
        """Queue an hdel operation."""
        self._commands.append(('hdel', (name, *keys), {}))
        return self

    def hget(self, name: str, key: str) -> 'FileCachePipeline':
        """Queue an hget operation."""
        self._commands.append(('hget', (name, key), {}))
        return self

    def hgetall(self, name: str) -> 'FileCachePipeline':
        """Queue an hgetall operation."""
        self._commands.append(('hgetall', (name,), {}))
        return self

    def delete(self, *keys: str) -> 'FileCachePipeline':
        """Queue a delete operation."""
        self._commands.append(('delete', keys, {}))
        return self

    def set(self, key: str, value: Any, **kwargs) -> 'FileCachePipeline':
        """Queue a set operation."""
        self._commands.append(('set', (key, value), kwargs))
        return self

    async def execute(self) -> list[Any]:
        """Execute all queued commands and return results."""
        results = []
        for method_name, args, kwargs in self._commands:
            method = getattr(self._cache, method_name)
            try:
                result = await method(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.debug(f"Pipeline command {method_name} failed: {e}")
                results.append(None)
        self._commands.clear()
        return results


class InMemoryPubSub:
    """In-memory Pub/Sub client using SimplePubSubBus."""

    def __init__(self):
        self.subscribed_channels: dict[str, any] = {}

    async def subscribe(self, *channels: str) -> None:
        """Subscribe to channels."""
        for ch in channels:
            if ch not in self.subscribed_channels:
                self.subscribed_channels[ch] = await in_memory_bus.subscribe(ch)

    async def unsubscribe(self, *channels: str) -> None:
        """Unsubscribe from channels."""
        for ch in channels:
            if ch in self.subscribed_channels:
                await in_memory_bus.unsubscribe(ch, self.subscribed_channels[ch])
                del self.subscribed_channels[ch]

    async def listen(self):
        """Async generator that yields messages from subscribed channels."""
        if not self.subscribed_channels:
            return
            yield  # Makes this an async generator

        # For simplicity, listen to the first subscribed channel
        # In practice, the frontend usually subscribes to one channel per connection
        first_channel = list(self.subscribed_channels.keys())[0]
        queue = self.subscribed_channels[first_channel]

        while True:
            msg = await queue.get()
            yield {"type": "message", "channel": first_channel, "data": msg}

    async def get_message(self, ignore_subscribe_messages: bool = False, timeout: float = None):
        """Get message from channel (non-blocking style with timeout)."""
        import asyncio
        if not self.subscribed_channels:
            return None

        first_channel = list(self.subscribed_channels.keys())[0]
        queue = self.subscribed_channels[first_channel]

        try:
            if timeout:
                msg = await asyncio.wait_for(queue.get(), timeout=timeout)
            else:
                msg = queue.get_nowait()
            return {"type": "message", "channel": first_channel, "data": msg}
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            return None

    async def close(self) -> None:
        """Close all subscriptions."""
        for ch, q in list(self.subscribed_channels.items()):
            await in_memory_bus.unsubscribe(ch, q)
        self.subscribed_channels.clear()


class NoOpPubSub:
    """No-op Pub/Sub client for file cache (deprecated, use InMemoryPubSub)."""

    async def subscribe(self, *channels: str) -> None:
        pass

    async def unsubscribe(self, *channels: str) -> None:
        pass

    async def listen(self):
        """Async generator that never yields."""
        return
        yield  # Makes this an async generator

    async def get_message(self, ignore_subscribe_messages: bool = False, timeout: float = None):
        """Get message from channel (no-op, returns None)."""
        return None

    async def close(self) -> None:
        pass


# Singleton instance
_file_cache: Optional[FileCache] = None


def get_file_cache() -> FileCache:
    """Get singleton FileCache instance."""
    global _file_cache
    if _file_cache is None:
        _file_cache = FileCache()
    return _file_cache
