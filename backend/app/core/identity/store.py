import logging

from app.infrastructure.cache import cache

logger = logging.getLogger(__name__)

TOKEN_HASH_KEY = "evoloop:tokens"

# Hash field names
FIELD_ACCESS_TOKEN = "access_token"
FIELD_REFRESH_TOKEN = "refresh_token"
FIELD_MEMBER_ID = "member_id"
FIELD_DEVICE_KEY = "device_key"


class IdentityStore:
    """
    Token storage backed by the unified cache infrastructure.

    Uses cache hash operations to store tokens, providing:
    - Cross-process synchronization (FileCache with fcntl flock in embedded mode)
    - Cross-instance synchronization (RedisCache with distributed locks in production)

    The underlying backend is selected automatically based on EMBEDDED_MODE:
    - EMBEDDED_MODE=true  -> FileCache
    - EMBEDDED_MODE=false -> RedisCache
    """

    @classmethod
    async def save_access_token(cls, token: str) -> bool:
        await cache.hset(TOKEN_HASH_KEY, FIELD_ACCESS_TOKEN, token)
        return True

    @classmethod
    async def get_access_token(cls) -> str | None:
        val = await cache.hget(TOKEN_HASH_KEY, FIELD_ACCESS_TOKEN)
        return val if val is not None else None

    @classmethod
    async def delete_access_token(cls) -> bool:
        await cache.hdel(TOKEN_HASH_KEY, FIELD_ACCESS_TOKEN)
        return True

    @classmethod
    async def save_refresh_token(cls, token: str) -> bool:
        await cache.hset(TOKEN_HASH_KEY, FIELD_REFRESH_TOKEN, token)
        return True

    @classmethod
    async def get_refresh_token(cls) -> str | None:
        val = await cache.hget(TOKEN_HASH_KEY, FIELD_REFRESH_TOKEN)
        return val if val is not None else None

    @classmethod
    async def delete_refresh_token(cls) -> bool:
        await cache.hdel(TOKEN_HASH_KEY, FIELD_REFRESH_TOKEN)
        return True

    @classmethod
    async def save_device_key(cls, key: str) -> bool:
        await cache.hset(TOKEN_HASH_KEY, FIELD_DEVICE_KEY, key)
        return True

    @classmethod
    async def get_device_key(cls) -> str | None:
        val = await cache.hget(TOKEN_HASH_KEY, FIELD_DEVICE_KEY)
        return val if val is not None else None

    @classmethod
    async def delete_device_key(cls) -> bool:
        await cache.hdel(TOKEN_HASH_KEY, FIELD_DEVICE_KEY)
        return True

    @classmethod
    async def save_member_id(cls, member_id: int) -> bool:
        await cache.hset(TOKEN_HASH_KEY, FIELD_MEMBER_ID, str(member_id))
        return True

    @classmethod
    async def get_member_id(cls) -> int | None:
        val = await cache.hget(TOKEN_HASH_KEY, FIELD_MEMBER_ID)
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    @classmethod
    async def delete_member_id(cls) -> bool:
        await cache.hdel(TOKEN_HASH_KEY, FIELD_MEMBER_ID)
        return True

    @classmethod
    async def get_all(cls) -> dict:
        """Return all stored token fields as a dict."""
        return await cache.hgetall(TOKEN_HASH_KEY)

    @classmethod
    async def clear(cls) -> bool:
        """Delete the entire token hash."""
        await cache.delete(TOKEN_HASH_KEY)
        return True
