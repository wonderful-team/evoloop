"""
Low-level FileCache Implementation
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

from app.utils.pubsub import in_memory_bus

logger = logging.getLogger(__name__)


class _FileCacheCore:
    def __init__(self, cache_dir: str | None = None):
        if cache_dir is None:
            from app.core.config import settings
            cache_dir = os.path.join(settings.APP_DATA_DIR, "cache")
        self.cache_dir = Path(cache_dir)
        self._ensure_directories()

    def _ensure_directories(self):
        for subdir in ["strings", "hashes", "sets", "lists"]:
            (self.cache_dir / subdir).mkdir(parents=True, exist_ok=True)

    def _get_path(self, category: str, name: str) -> Path:
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        return self.cache_dir / category / f"{safe_name}.json"

    def _read(self, category: str, name: str) -> Any:
        path = self._get_path(category, name)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.debug(f"Cache read error for {category}/{name}: {e}")
            return None

    def _write(self, category: str, name: str, data: Any) -> bool:
        path = self._get_path(category, name)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except OSError as e:
            logger.debug(f"Cache write error for {category}/{name}: {e}")
            return False

    def _delete(self, category: str, name: str) -> bool:
        path = self._get_path(category, name)
        try:
            if path.exists():
                path.unlink()
            return True
        except OSError as e:
            logger.debug(f"Cache delete error for {category}/{name}: {e}")
            return False

    async def get(self, key: str) -> Any | None:
        return self._read("strings", key)

    async def set(self, key: str, value: Any, **kwargs) -> bool:
        return self._write("strings", key, value)

    async def setex(self, key: str, time: int, value: Any) -> bool:
        return self._write("strings", key, value)

    async def delete(self, *keys: str) -> int:
        count = 0
        for category in ["strings", "hashes", "sets", "lists"]:
            for key in keys:
                if self._delete(category, key):
                    count += 1
        return count

    async def exists(self, key: str) -> bool:
        for category in ["strings", "hashes", "sets", "lists"]:
            path = self._get_path(category, key)
            if path.exists():
                return True
        return False

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def incr(self, key: str, amount: int = 1) -> int:
        data = self._read("strings", key)
        try:
            current = int(data) if data is not None else 0
        except (ValueError, TypeError):
            current = 0
        new_value = current + amount
        self._write("strings", key, new_value)
        return new_value

    async def hget(self, name: str, key: str) -> Any | None:
        data = self._read("hashes", name)
        if data and isinstance(data, dict):
            return data.get(key)
        return None

    async def hset(self, name: str, key: str | None = None, value: Any = None, mapping: dict | None = None) -> int:
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
        data = self._read("hashes", name)
        return data if isinstance(data, dict) else {}

    async def hdel(self, name: str, *keys: str) -> int:
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
        data = self._read("hashes", name)
        return len(data) if isinstance(data, dict) else 0

    async def sadd(self, name: str, *values: Any) -> int:
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

    async def scard(self, name: str) -> int:
        data = self._read("sets", name)
        return len(data) if isinstance(data, list) else 0

    async def srem(self, name: str, *values: Any) -> int:
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
        data = self._read("sets", name)
        return set(data) if isinstance(data, list) else set()

    async def sismember(self, name: str, value: Any) -> bool:
        data = self._read("sets", name)
        if isinstance(data, list):
            return value in data
        return False

    async def lpush(self, name: str, *values: Any) -> int:
        data = self._read("lists", name)
        if not isinstance(data, list):
            data = []
        for value in reversed(values):
            data.insert(0, value)
        self._write("lists", name, data)
        return len(data)

    async def ltrim(self, name: str, start: int, end: int) -> bool:
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

    async def lrange(self, name: str, start: int, end: int) -> list:
        data = self._read("lists", name)
        if not isinstance(data, list):
            return []
        if end < 0:
            end = len(data) + end + 1
        else:
            end = end + 1
        return data[start:end]

    async def publish(self, channel: str, message: Any) -> int:
        await in_memory_bus.publish(channel, message)
        return 1

    async def keys(self, pattern: str = "*") -> list[str]:
        import fnmatch
        result = []
        for category in ["strings", "hashes", "sets", "lists"]:
            dir_path = self.cache_dir / category
            if not dir_path.exists():
                continue
            for f in dir_path.iterdir():
                if f.suffix == ".json":
                    key = f.stem
                    if fnmatch.fnmatch(key, pattern):
                        result.append(key)
        return result

    async def aclose(self) -> None:
        pass


class FileCacheCore:
    def __init__(self, cache_dir: str | None = None):
        self._core = _FileCacheCore(cache_dir=cache_dir)

    async def get(self, key: str) -> Any | None:
        return await self._core.get(key)

    async def set(self, key: str, value: Any, **kwargs) -> bool:
        return await self._core.set(key, value, **kwargs)

    async def setex(self, key: str, time: int, value: Any) -> bool:
        return await self._core.setex(key, time, value)

    async def delete(self, *keys: str) -> int:
        return await self._core.delete(*keys)

    async def exists(self, *keys: str) -> int:
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

    async def hlen(self, name: str) -> int:
        return await self._core.hlen(name)

    async def sadd(self, name: str, *values: Any) -> int:
        return await self._core.sadd(name, *values)

    async def scard(self, name: str) -> int:
        return await self._core.scard(name)

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
        return await self._core.lrange(name, start, end)

    async def keys(self, pattern: str = "*", **kwargs) -> list[str]:
        return await self._core.keys(pattern)
