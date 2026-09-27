"""
Cache services — rate limiting.

ActivityStateService and ContextCacheService have been moved to core layer.
"""

from app.infrastructure.cache import get_cache
from app.infrastructure.cache.abstract import Cache


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
