"""
Redis client for EvoLoop Backend.

Supports two modes:
- Full mode: Real Redis connection
- Embedded mode: FileCache with in-memory Pub/Sub
"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def _create_redis_client():
    """Create Redis client or FileCache based on configuration."""
    if settings.EMBEDDED_MODE:
        logger.debug("[Redis] Using FileCache (embedded mode)")
        from app.infrastructure.cache.file_cache import get_file_cache
        return get_file_cache()

    try:
        import redis.asyncio as redis

        pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL or "redis://localhost:6379/0",
            encoding="utf-8",
            decode_responses=True,
            max_connections=120,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True
        )
        logger.info("[Redis] Connected to Redis")
        return redis.Redis(connection_pool=pool)
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise


def _create_pubsub_client():
    """Create Pub/Sub client or FileCache based on configuration."""
    if settings.EMBEDDED_MODE:
        logger.debug("[PubSub] Using FileCache (embedded mode)")
        from app.infrastructure.cache.file_cache import get_file_cache
        return get_file_cache()

    try:
        import redis.asyncio as redis

        pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL or "redis://localhost:6379/0",
            encoding="utf-8",
            decode_responses=True,
            max_connections=500,
            socket_timeout=None,
            socket_connect_timeout=5.0,
            retry_on_timeout=True
        )
        return redis.Redis(connection_pool=pool)
    except Exception as e:
        logger.error(f"Failed to connect to Redis PubSub: {e}")
        raise


async def _cleanup_redis(client):
    if hasattr(client, 'aclose'):
        await client.aclose()


try:
    from app.utils.async_utils import LoopBoundResource

    _redis_pool = LoopBoundResource(_create_redis_client, _cleanup_redis)
    _pubsub_pool = LoopBoundResource(_create_pubsub_client, _cleanup_redis)

    class RedisProxy:
        def __init__(self, resource_pool):
            self._pool = resource_pool

        def __getattr__(self, name):
            return getattr(self._pool.get(), name)

    # Proxy instances for compatibility
    redis_client = RedisProxy(_redis_pool)
    redis_pubsub_client = RedisProxy(_pubsub_pool)

    async def get_redis_client():
        """Get current loop's Redis client singleton."""
        return _redis_pool.get()

except ImportError:
    # Fallback for when LoopBoundResource is not available
    from app.infrastructure.cache.file_cache import get_file_cache

    redis_client = get_file_cache()
    redis_pubsub_client = get_file_cache()

    async def get_redis_client():
        return get_file_cache()


__all__ = ["redis_client", "redis_pubsub_client", "get_redis_client"]
