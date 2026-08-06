"""
Cache services — rate limiting, user/link token caching.

ActivityStateService and ContextCacheService have been moved to core layer.
Re-exports are kept for backward compatibility.
"""

import json
import logging

from app.infrastructure.cache import get_cache
from app.infrastructure.cache.abstract import Cache

logger = logging.getLogger(__name__)


class UserCacheService:
    """
    Service for caching user data.

    Keys:
        evoloop:user:{member_id} -> User data dict
    """

    KEY_PREFIX = "evoloop:user"
    DEFAULT_TTL = 86400

    def __init__(self, backend: Cache | None = None):
        self._cache = backend or get_cache()

    def _key(self, member_id: str | int) -> str:
        return f"{self.KEY_PREFIX}:{member_id}"

    async def get_user(self, member_id: str | int) -> dict | None:
        data = await self._cache.get(self._key(member_id))
        if data is None:
            return None
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid user cache data for {member_id}")
                return None
        return data if isinstance(data, dict) else None

    async def set_user(self, member_id: str | int, user_data: dict, ttl: int | None = None) -> bool:
        return await self._cache.set(
            self._key(member_id),
            user_data,
            ex=ttl or self.DEFAULT_TTL
        )

    async def delete_user(self, member_id: str | int) -> bool:
        return await self._cache.delete(self._key(member_id)) > 0


class RateLimitService:
    """
    Service for rate limiting.

    Keys:
        ratelimit:{endpoint}:{identifier} -> Request count
    """

    KEY_PREFIX = "ratelimit"
    DEFAULT_WINDOW = 86400

    def __init__(self, backend: Cache | None = None):
        self._cache = backend or get_cache()

    def _key(self, endpoint: str, identifier: str) -> str:
        return f"{self.KEY_PREFIX}:{endpoint}:{identifier}"

    async def increment(self, endpoint: str, identifier: str, window: int | None = None) -> int:
        key = self._key(endpoint, identifier)
        count = await self._cache.incr(key)
        if count == 1:
            await self._cache.expire(key, window or self.DEFAULT_WINDOW)
        return count

    async def get_count(self, endpoint: str, identifier: str) -> int:
        count = await self._cache.get(self._key(endpoint, identifier))
        return int(count) if count else 0

    async def reset(self, endpoint: str, identifier: str) -> bool:
        return await self._cache.delete(self._key(endpoint, identifier)) > 0


class LinkTokenService:
    """
    Service for temporary link tokens.

    Keys:
        evoloop:link:token -> Token data
    """

    KEY_PREFIX = "evoloop:link"

    def __init__(self, backend: Cache | None = None):
        self._cache = backend or get_cache()

    async def store_token(self, token_name: str, token_data: str, ttl: int = 3600) -> bool:
        return await self._cache.set(
            f"{self.KEY_PREFIX}:{token_name}",
            token_data,
            ex=ttl
        )

    async def get_token(self, token_name: str) -> str | None:
        data = await self._cache.get(f"{self.KEY_PREFIX}:{token_name}")
        return data if isinstance(data, str) else None
