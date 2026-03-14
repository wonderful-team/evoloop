"""
Cloud Data Cache for EvoLoop Client.

Caches hot data from EvoLoop Cloud to reduce latency
and enable offline operation.
"""

import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, asdict

from app.core.config import settings
from app.logging import logger


@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    key: str
    data: Any
    cached_at: datetime
    ttl_seconds: int
    source: str  # "cloud", "local", "fallback"
    hit_count: int = 0

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        elapsed = (datetime.utcnow() - self.cached_at).total_seconds()
        return elapsed > self.ttl_seconds

    def touch(self):
        """Increment hit count."""
        self.hit_count += 1


class CloudDataCache:
    """
    Local cache for cloud data.

    Provides:
    - In-memory cache for hot data (LTM queries, Atlas elements)
    - Disk persistence for offline availability
    - TTL-based expiration
    - LRU eviction
    """

    _instance: Optional["CloudDataCache"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        cache_dir: str = None,
        memory_size: int = 1000,
        default_ttl: int = 3600,
    ):
        if self._initialized:
            return

        self.cache_dir = Path(cache_dir or settings.APP_DATA_DIR) / "cloud_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.memory_size = memory_size
        self.default_ttl = default_ttl

        # In-memory cache
        self._memory: dict[str, CacheEntry] = {}

        # Statistics
        self._hits = 0
        self._misses = 0

        self._initialized = True
        logger.info(f"[CloudCache] Initialized at {self.cache_dir}")

    def get(self, key: str) -> Optional[Any]:
        """
        Get data from cache.

        Tries memory first, then disk.
        Returns None if not found or expired.
        """
        # Check memory
        if key in self._memory:
            entry = self._memory[key]
            if not entry.is_expired():
                entry.touch()
                self._hits += 1
                logger.debug(f"[CloudCache] Memory hit: {key}")
                return entry.data
            else:
                # Expired, remove from memory
                del self._memory[key]

        # Check disk
        disk_data = self._load_from_disk(key)
        if disk_data is not None:
            # Promote to memory
            self._store_in_memory(key, disk_data, self.default_ttl, "cloud")
            self._hits += 1
            logger.debug(f"[CloudCache] Disk hit: {key}")
            return disk_data

        self._misses += 1
        return None

    def set(
        self,
        key: str,
        data: Any,
        ttl: int = None,
        source: str = "cloud",
    ) -> None:
        """
        Store data in cache.

        Stores in both memory and disk.
        """
        ttl = ttl or self.default_ttl

        # Store in memory
        self._store_in_memory(key, data, ttl, source)

        # Store on disk
        self._save_to_disk(key, data, ttl, source)

        logger.debug(f"[CloudCache] Stored: {key} (TTL: {ttl}s)")

    def invalidate(self, key: str) -> bool:
        """Remove specific key from cache."""
        removed = False

        if key in self._memory:
            del self._memory[key]
            removed = True

        disk_path = self._disk_path(key)
        if disk_path.exists():
            disk_path.unlink()
            removed = True

        if removed:
            logger.debug(f"[CloudCache] Invalidated: {key}")

        return removed

    def invalidate_pattern(self, pattern: str) -> int:
        """Remove all keys matching pattern."""
        count = 0

        # Memory
        keys_to_remove = [k for k in self._memory.keys() if pattern in k]
        for key in keys_to_remove:
            del self._memory[key]
            count += 1

        # Disk
        for cache_file in self.cache_dir.glob("*.json"):
            if pattern in cache_file.stem:
                cache_file.unlink()
                count += 1

        logger.info(f"[CloudCache] Invalidated {count} entries matching '{pattern}'")
        return count

    def clear(self) -> None:
        """Clear all cache."""
        self._memory.clear()

        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()

        logger.info("[CloudCache] Cleared all cache")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0

        return {
            "memory_entries": len(self._memory),
            "disk_entries": len(list(self.cache_dir.glob("*.json"))),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "cache_dir": str(self.cache_dir),
        }

    def _store_in_memory(self, key: str, data: Any, ttl: int, source: str) -> None:
        """Store in memory cache with LRU eviction."""
        # Evict if at capacity
        if len(self._memory) >= self.memory_size:
            # Find least recently used (lowest hit count)
            lru_key = min(self._memory.keys(), key=lambda k: self._memory[k].hit_count)
            del self._memory[lru_key]
            logger.debug(f"[CloudCache] Evicted LRU: {lru_key}")

        self._memory[key] = CacheEntry(
            key=key,
            data=data,
            cached_at=datetime.utcnow(),
            ttl_seconds=ttl,
            source=source,
        )

    def _save_to_disk(self, key: str, data: Any, ttl: int, source: str) -> None:
        """Persist to disk."""
        disk_path = self._disk_path(key)

        entry_data = {
            "key": key,
            "data": data,
            "cached_at": datetime.utcnow().isoformat(),
            "ttl_seconds": ttl,
            "source": source,
        }

        with open(disk_path, "w") as f:
            json.dump(entry_data, f, default=str)

    def _load_from_disk(self, key: str) -> Optional[Any]:
        """Load from disk if exists and not expired."""
        disk_path = self._disk_path(key)

        if not disk_path.exists():
            return None

        try:
            with open(disk_path) as f:
                entry_data = json.load(f)

            cached_at = datetime.fromisoformat(entry_data["cached_at"])
            ttl = entry_data["ttl_seconds"]

            if (datetime.utcnow() - cached_at).total_seconds() > ttl:
                # Expired
                disk_path.unlink()
                return None

            return entry_data["data"]

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"[CloudCache] Failed to load {key}: {e}")
            disk_path.unlink()
            return None

    def _disk_path(self, key: str) -> Path:
        """Get disk path for key."""
        # Hash key for safe filename
        hashed = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{hashed}.json"


# Specialized cache classes for different data types

class LTMCache:
    """Cache for Long-Term Memory queries."""

    def __init__(self, cache: CloudDataCache = None):
        self.cache = cache or CloudDataCache()
        self.default_ttl = 1800  # 30 minutes

    def _make_key(self, query: str, memory_types: list[str]) -> str:
        """Generate cache key for LTM query."""
        type_str = ",".join(sorted(memory_types))
        return f"ltm:{type_str}:{query.lower().strip()}"

    def get(self, query: str, memory_types: list[str]) -> Optional[list[dict]]:
        """Get cached LTM results."""
        key = self._make_key(query, memory_types)
        return self.cache.get(key)

    def set(self, query: str, memory_types: list[str], memories: list[dict]) -> None:
        """Cache LTM results."""
        key = self._make_key(query, memory_types)
        self.cache.set(key, memories, ttl=self.default_ttl)

    def invalidate_for_query(self, query: str) -> int:
        """Invalidate all cache entries matching query."""
        return self.cache.invalidate_pattern(f"ltm:*:{query.lower().strip()}")


class AtlasCache:
    """Cache for Atlas (UI element) queries."""

    def __init__(self, cache: CloudDataCache = None):
        self.cache = cache or CloudDataCache()
        self.default_ttl = 86400  # 24 hours - UI structures don't change often

    def _make_key(self, app_id: str, element_desc: str) -> str:
        """Generate cache key for Atlas query."""
        return f"atlas:{app_id}:{element_desc.lower().strip()}"

    def get(self, app_id: str, element_desc: str) -> Optional[list[dict]]:
        """Get cached Atlas results."""
        key = self._make_key(app_id, element_desc)
        return self.cache.get(key)

    def set(self, app_id: str, element_desc: str, elements: list[dict]) -> None:
        """Cache Atlas results."""
        key = self._make_key(app_id, element_desc)
        self.cache.set(key, elements, ttl=self.default_ttl)

    def invalidate_app(self, app_id: str) -> int:
        """Invalidate all cache entries for an app."""
        return self.cache.invalidate_pattern(f"atlas:{app_id}:")


class SkillCache:
    """Cache for downloaded skills."""

    def __init__(self, cache: CloudDataCache = None):
        self.cache = cache or CloudDataCache()
        self.default_ttl = 604800  # 7 days

    def get(self, skill_id: str) -> Optional[dict]:
        """Get cached skill package."""
        key = f"skill:{skill_id}"
        return self.cache.get(key)

    def set(self, skill_id: str, skill_package: dict) -> None:
        """Cache skill package."""
        key = f"skill:{skill_id}"
        self.cache.set(key, skill_package, ttl=self.default_ttl)


# Global cache instances
_cloud_cache: Optional[CloudDataCache] = None
_ltm_cache: Optional[LTMCache] = None
_atlas_cache: Optional[AtlasCache] = None
_skill_cache: Optional[SkillCache] = None


def get_cloud_cache() -> CloudDataCache:
    """Get global cloud data cache."""
    global _cloud_cache
    if _cloud_cache is None:
        _cloud_cache = CloudDataCache()
    return _cloud_cache


def get_ltm_cache() -> LTMCache:
    """Get global LTM cache."""
    global _ltm_cache
    if _ltm_cache is None:
        _ltm_cache = LTMCache(get_cloud_cache())
    return _ltm_cache


def get_atlas_cache() -> AtlasCache:
    """Get global Atlas cache."""
    global _atlas_cache
    if _atlas_cache is None:
        _atlas_cache = AtlasCache(get_cloud_cache())
    return _atlas_cache


def get_skill_cache() -> SkillCache:
    """Get global skill cache."""
    global _skill_cache
    if _skill_cache is None:
        _skill_cache = SkillCache(get_cloud_cache())
    return _skill_cache
