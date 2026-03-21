"""
Cache infrastructure for EvoLoop Backend.

Provides a unified cache interface that works with both cache backends (production)
and FileCache (embedded mode).

Usage:
    from app.infrastructure.cache import cache
    
    # Key-value operations
    await cache.set("key", value, ex=3600)
    value = await cache.get("key")
    
    # Hash operations
    await cache.hset("hash_name", mapping={"field": "value"})
    data = await cache.hgetall("hash_name")
    
    # Pub/Sub for real-time events
    pubsub = cache.pubsub()
    await pubsub.subscribe("channel")
    message = await pubsub.get_message(timeout=1.0)
    
    # Pipeline for batch operations
    pipe = cache.pipeline()
    pipe.get("key1").hgetall("hash1")
    results = await pipe.execute()
"""

import logging
from typing import TYPE_CHECKING, Optional

from app.core.config import settings

if TYPE_CHECKING:
    from app.infrastructure.cache.abstract import Cache

logger = logging.getLogger(__name__)

# Global cache backend instance
_cache_instance: Optional["Cache"] = None


def get_cache() -> "Cache":
    """
    Get the global cache backend instance.
    
    Creates the instance on first call based on EMBEDDED_MODE setting.
    """
    global _cache_instance
    
    if _cache_instance is not None:
        return _cache_instance
    
    if settings.EMBEDDED_MODE:
        logger.info("[Cache] Using FileCache (embedded mode)")
        from app.infrastructure.cache.file import FileCache
        _cache_instance = FileCache()
    else:
        logger.info("[Cache] Using RedisCache (production mode)")
        from app.infrastructure.cache.redis import RedisCache
        _cache_instance = RedisCache()
    
    return _cache_instance


# Convenience exports
cache = get_cache()

__all__ = [
    "cache",
    "get_cache",
    "Cache",
    "CachePipeline",
    "CacheLock",
    "PubSubBackend",
]
