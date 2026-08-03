"""Context cache service — caches EvoContext between agent runs."""

from app.infrastructure.cache import get_cache
from app.infrastructure.cache.abstract import Cache


class ContextCacheService:
    """
    Service for caching EvoContext between agent runs.

    Keys:
        evoloop:context:{thread_id} -> Context data
    """

    KEY_PREFIX = "evoloop:context"
    DEFAULT_TTL = 604800  # 7 days

    def __init__(self, backend: Cache | None = None):
        self._cache = backend or get_cache()

    def _key(self, thread_id: str) -> str:
        return f"{self.KEY_PREFIX}:{thread_id}"

    async def save_context(self, thread_id: str, context_data: dict) -> bool:
        """Save context data."""
        return await self._cache.hset(self._key(thread_id), mapping=context_data) > 0

    async def load_context(self, thread_id: str) -> dict | None:
        """Load context data."""
        return await self._cache.hgetall(self._key(thread_id))
