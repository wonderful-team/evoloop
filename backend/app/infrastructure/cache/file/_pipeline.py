"""
Pipeline adapter for FileCache.
"""

import logging
from typing import TYPE_CHECKING, Any

from app.infrastructure.cache.abstract import CachePipeline

if TYPE_CHECKING:
    from app.infrastructure.cache.file._core import FileCacheCore

logger = logging.getLogger(__name__)


class FileCachePipelineAdapter(CachePipeline):
    def __init__(self, backend: "FileCacheCore"):
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

    def hlen(self, name: str) -> "FileCachePipelineAdapter":
        self._commands.append(("hlen", (name,), {}))
        return self

    def sadd(self, name: str, *values: Any) -> "FileCachePipelineAdapter":
        self._commands.append(("sadd", (name,) + values, {}))
        return self

    def scard(self, name: str) -> "FileCachePipelineAdapter":
        self._commands.append(("scard", (name,), {}))
        return self

    def srem(self, name: str, *values: Any) -> "FileCachePipelineAdapter":
        self._commands.append(("srem", (name,) + values, {}))
        return self

    def lpush(self, name: str, *values: Any) -> "FileCachePipelineAdapter":
        self._commands.append(("lpush", (name,) + values, {}))
        return self

    def ltrim(self, name: str, start: int, end: int) -> "FileCachePipelineAdapter":
        self._commands.append(("ltrim", (name, start, end), {}))
        return self

    async def execute(self) -> list[Any]:
        results = []
        for method_name, args, kwargs in self._commands:
            method = getattr(self._backend, method_name)
            try:
                result = await method(*args, **kwargs)
                results.append(result)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.debug("Pipeline command %s failed: %s", method_name, e)
                results.append(None)
        self._commands.clear()
        return results
