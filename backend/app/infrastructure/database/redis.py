import redis.asyncio as redis

from app.core.config import settings
from app.utils.async_utils import LoopBoundResource


async def _cleanup_redis(client: redis.Redis):
    await client.aclose()


def _create_redis_client() -> redis.Redis:
    pool = redis.ConnectionPool.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=120,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
        retry_on_timeout=True
    )
    return redis.Redis(connection_pool=pool)


def _create_pubsub_client() -> redis.Redis:
    pool = redis.ConnectionPool.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=500,
        socket_timeout=None,
        socket_connect_timeout=5.0,
        retry_on_timeout=True
    )
    return redis.Redis(connection_pool=pool)


_redis_pool = LoopBoundResource(_create_redis_client, _cleanup_redis)
_pubsub_pool = LoopBoundResource(_create_pubsub_client, _cleanup_redis)


class RedisProxy:
    def __init__(self, resource_pool: LoopBoundResource):
        self._pool = resource_pool

    def __getattr__(self, name):
        return getattr(self._pool.get(), name)


# 代理实例，兼容老代码直接使用 redis_client.xxx
redis_client: redis.Redis = RedisProxy(_redis_pool)  # type: ignore
redis_pubsub_client: redis.Redis = RedisProxy(_pubsub_pool)  # type: ignore


async def get_redis_client() -> redis.Redis:
    """获取当前 Loop 的 Redis 客户端单例。"""
    return _redis_pool.get()

