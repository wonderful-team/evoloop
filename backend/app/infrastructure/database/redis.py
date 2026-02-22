import redis.asyncio as redis
from app.core.config import settings

# 全局 Redis 连接池
pool = redis.ConnectionPool.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
    max_connections=120,
    socket_timeout=5.0,
    socket_connect_timeout=5.0,
    retry_on_timeout=True
)

# 全局 Redis 客户端实例
redis_client: redis.Redis = redis.Redis(connection_pool=pool)

# 专用 Pub/Sub 连接池 (SSE等长连接场景，不设 socket_timeout，更大连接数防耗尽)
pubsub_pool = redis.ConnectionPool.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
    max_connections=500,
    socket_timeout=None,
    socket_connect_timeout=5.0,
    retry_on_timeout=True
)

# 专用 Pub/Sub 客户端实例
redis_pubsub_client: redis.Redis = redis.Redis(connection_pool=pubsub_pool)


async def get_redis_client() -> redis.Redis:
    """
    获取 Redis 客户端单例。
    """
    return redis_client
