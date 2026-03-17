"""
Redis client for EvoLoop Backend.

Supports two modes:
- Full mode: Real Redis connection
- Embedded mode: No-op (caching disabled)
"""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# In-Memory Pub/Sub for Embedded Mode (SSE Support)
# =============================================================================

from app.utils.pubsub import in_memory_bus

class NoOpRedis:
    """Redis client for embedded mode.
    
    Now supports In-Memory Pub/Sub for SSE functionality.
    """

    async def get(self, key: str) -> None:
        return None

    async def set(self, key: str, value: Any, **kwargs) -> bool:
        return True

    async def setex(self, key: str, time: int, value: Any) -> bool:
        return True

    async def delete(self, *keys: str) -> int:
        return 0

    async def exists(self, *keys: str) -> int:
        return 0

    async def expire(self, key: str, time: int) -> bool:
        return True

    async def ttl(self, key: str) -> int:
        return -2

    async def keys(self, pattern: str = "*") -> list:
        return []

    async def scan(self, cursor: int = 0, match: str = None, count: int = None):
        return (0, [])

    async def hget(self, name: str, key: str) -> None:
        return None

    async def hset(self, name: str, key: str = None, value: Any = None, mapping: dict = None) -> int:
        return 0

    async def hgetall(self, name: str) -> dict:
        return {}

    async def hdel(self, name: str, *keys: str) -> int:
        return 0

    async def hlen(self, name: str) -> int:
        return 0

    async def sadd(self, name: str, *values: Any) -> int:
        return 0

    async def srem(self, name: str, *values: Any) -> int:
        return 0

    async def smembers(self, name: str) -> set:
        return set()

    async def sismember(self, name: str, value: Any) -> bool:
        return False

    async def scard(self, name: str) -> int:
        return 0

    async def lpush(self, name: str, *values: Any) -> int:
        return 0

    async def rpush(self, name: str, *values: Any) -> int:
        return 0

    async def lpop(self, name: str, count: int = None) -> Any:
        return None

    async def rpop(self, name: str, count: int = None) -> Any:
        return None

    async def lrange(self, name: str, start: int, end: int) -> list:
        return []

    async def llen(self, name: str) -> int:
        return 0

    async def publish(self, channel: str, message: Any) -> int:
        """Publish message to in-memory bus."""
        await in_memory_bus.publish(channel, message)
        return 1

    async def aclose(self) -> None:
        pass

    def pubsub(self, **kwargs):
        return NoOpPubSub()


class NoOpPubSub:
    """In-memory Pub/Sub client for embedded mode."""

    def __init__(self):
        import asyncio
        self.subscribed_channels: dict[str, asyncio.Queue] = {}

    async def subscribe(self, *channels: str) -> None:
        for ch in channels:
            if ch not in self.subscribed_channels:
                self.subscribed_channels[ch] = await in_memory_bus.subscribe(ch)

    async def unsubscribe(self, *channels: str) -> None:
        for ch in channels:
            if ch in self.subscribed_channels:
                await in_memory_bus.unsubscribe(ch, self.subscribed_channels[ch])
                del self.subscribed_channels[ch]

    async def listen(self):
        """Async generator that yields messages from all subscribed channels."""
        if not self.subscribed_channels:
            return
            
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
        for ch, q in self.subscribed_channels.items():
            await in_memory_bus.unsubscribe(ch, q)
        self.subscribed_channels.clear()


# =============================================================================
# Redis Client Factory
# =============================================================================

def _create_redis_client():
    """Create Redis client, FileCache, or NoOp based on configuration."""
    if settings.EMBEDDED_MODE:
        logger.debug("[Redis] Using FileCache (embedded mode)")
        try:
            from app.infrastructure.cache.file_cache import get_file_cache
            return get_file_cache()
        except Exception as e:
            logger.warning(f"Failed to initialize FileCache: {e}, falling back to NoOp")
            return NoOpRedis()

    if not settings.USE_REDIS:
        logger.debug("[Redis] Using NoOp client (Redis disabled)")
        return NoOpRedis()

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
    except ImportError:
        logger.warning("Redis not installed, using NoOp client")
        return NoOpRedis()
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        logger.warning("Falling back to NoOp Redis client")
        return NoOpRedis()


def _create_pubsub_client():
    """Create Pub/Sub client, FileCache, or NoOp based on configuration."""
    if settings.EMBEDDED_MODE:
        logger.debug("[PubSub] Using FileCache (embedded mode)")
        try:
            from app.infrastructure.cache.file_cache import get_file_cache
            return get_file_cache()
        except Exception:
            return NoOpRedis()

    if not settings.USE_REDIS:
        return NoOpRedis()

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
    except Exception:
        return NoOpRedis()


# =============================================================================
# Compatibility: Try to use LoopBoundResource for real Redis
# =============================================================================

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
    # Fallback: Direct NoOp instances
    redis_client = NoOpRedis()
    redis_pubsub_client = NoOpRedis()


    async def get_redis_client():
        return NoOpRedis()


__all__ = ["redis_client", "redis_pubsub_client", "get_redis_client", "NoOpRedis"]

