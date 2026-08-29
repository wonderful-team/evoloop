import logging

from app.core.identity import constants as identity_constants
from app.infrastructure.cache import cache

logger = logging.getLogger(__name__)


class IdentityStore:
    """
    Token storage backed by the unified cache infrastructure.

    Uses cache hash operations to store tokens, providing:
    - Cross-process synchronization (FileCache with fcntl flock in embedded mode)
    - Cross-instance synchronization (RedisCache with distributed locks in production)

    The underlying backend is selected automatically based on EMBEDDED_MODE:
    - EMBEDDED_MODE=true  -> FileCache
    - EMBEDDED_MODE=false -> RedisCache

    Device key is stored in a SEPARATE hash (evoloop:device:identity) but is now
    cleared during logout to ensure proper account separation and prevent
    DEVICE_NOT_BELONGS errors upon account switching.
    """

    # --- Token fields (survive in evoloop:tokens, cleared on logout) ---

    @classmethod
    async def save_access_token(cls, token: str) -> bool:
        await cache.hset(
            identity_constants.TOKEN_HASH_KEY,
            identity_constants.FIELD_ACCESS_TOKEN,
            token,
        )
        return True

    @classmethod
    async def get_access_token(cls) -> str | None:
        val = await cache.hget(
            identity_constants.TOKEN_HASH_KEY, identity_constants.FIELD_ACCESS_TOKEN
        )
        return val if val is not None else None

    @classmethod
    async def save_refresh_token(cls, token: str) -> bool:
        await cache.hset(
            identity_constants.TOKEN_HASH_KEY,
            identity_constants.FIELD_REFRESH_TOKEN,
            token,
        )
        return True

    @classmethod
    async def get_refresh_token(cls) -> str | None:
        val = await cache.hget(
            identity_constants.TOKEN_HASH_KEY, identity_constants.FIELD_REFRESH_TOKEN
        )
        return val if val is not None else None

    @classmethod
    async def save_member_id(cls, member_id: int) -> bool:
        await cache.hset(
            identity_constants.TOKEN_HASH_KEY,
            identity_constants.FIELD_MEMBER_ID,
            str(member_id),
        )
        return True

    @classmethod
    async def get_member_id(cls) -> int | None:
        val = await cache.hget(
            identity_constants.TOKEN_HASH_KEY, identity_constants.FIELD_MEMBER_ID
        )
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    # --- Device key (stored separately, survives logout) ---

    @classmethod
    async def save_device_key(cls, key: str) -> bool:
        await cache.hset(
            identity_constants.DEVICE_IDENTITY_HASH_KEY,
            identity_constants.FIELD_DEVICE_KEY,
            key,
        )
        return True

    @classmethod
    async def get_device_key(cls) -> str | None:
        val = await cache.hget(
            identity_constants.DEVICE_IDENTITY_HASH_KEY,
            identity_constants.FIELD_DEVICE_KEY,
        )
        return val if val is not None else None

    @classmethod
    async def delete_device_key(cls) -> bool:
        await cache.hdel(
            identity_constants.DEVICE_IDENTITY_HASH_KEY,
            identity_constants.FIELD_DEVICE_KEY,
        )
        return True

    @classmethod
    async def get_all(cls) -> dict:
        """Return all stored token fields as a dict."""
        return await cache.hgetall(identity_constants.TOKEN_HASH_KEY)

    @classmethod
    async def clear(cls) -> bool:
        """Delete the entire token hash and device identity."""
        await cache.delete(identity_constants.TOKEN_HASH_KEY)
        await cache.delete(identity_constants.DEVICE_IDENTITY_HASH_KEY)
        return True
