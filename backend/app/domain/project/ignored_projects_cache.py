"""
Ignored Projects Cache Manager

Manages caching of ignored project paths in Redis for fast lookup
during tree generation and file operations.
"""

import logging
from typing import Set

from sqlalchemy import select

from app.infrastructure.database.redis import redis_client
from app.infrastructure.database.sql.database import AsyncSessionLocal
from app.models import Repository

logger = logging.getLogger(__name__)

# Redis key for storing ignored project paths
REDIS_KEY_IGNORED_PATHS = "evoloop:ignored_project_paths"
# Cache TTL in seconds (10 minutes)
CACHE_TTL = 600


class IgnoredProjectsCache:
    """
    Cache manager for ignored project paths.

    Uses Redis as primary cache with PostgreSQL as fallback.
    Automatically refreshes cache on miss.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_ignored_paths(self, use_cache: bool = True) -> Set[str]:
        """
        Get set of ignored project paths.

        Args:
            use_cache: If True, try Redis first; if False, always query DB

        Returns:
            Set of absolute paths of ignored projects
        """
        if use_cache:
            # Try Redis first
            try:
                cached_paths = await redis_client.smembers(REDIS_KEY_IGNORED_PATHS)
                if cached_paths:
                    # Convert bytes to strings if needed
                    result = {p.decode() if isinstance(p, bytes) else p for p in cached_paths}
                    logger.debug(f"[IgnoredCache] Cache hit: {len(result)} paths")
                    return result
            except Exception as e:
                logger.warning(f"[IgnoredCache] Redis error: {e}. Falling back to DB.")

        # Cache miss or error - fetch from DB
        return await self._fetch_from_db_and_refresh_cache()

    async def _fetch_from_db_and_refresh_cache(self) -> Set[str]:
        """Fetch ignored paths from DB and refresh Redis cache."""
        paths = await self._fetch_from_db()

        # Update cache (best effort)
        try:
            if paths:
                # Clear old cache and add new paths
                pipe = redis_client.pipeline()
                pipe.delete(REDIS_KEY_IGNORED_PATHS)
                pipe.sadd(REDIS_KEY_IGNORED_PATHS, *paths)
                pipe.expire(REDIS_KEY_IGNORED_PATHS, CACHE_TTL)
                await pipe.execute()
                logger.debug(f"[IgnoredCache] Cache refreshed: {len(paths)} paths")
            else:
                # No ignored projects - set empty cache with TTL
                await redis_client.setex(REDIS_KEY_IGNORED_PATHS, CACHE_TTL, "")
        except Exception as e:
            logger.warning(f"[IgnoredCache] Failed to refresh cache: {e}")

        return paths

    async def _fetch_from_db(self) -> Set[str]:
        """Fetch ignored project paths directly from database."""
        paths = set()
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(Repository).where(Repository.sync_status == "IGNORED")
                result = await session.execute(stmt)
                repos = result.scalars().all()

                for repo in repos:
                    if repo.local_path:
                        paths.add(repo.local_path)

                logger.debug(f"[IgnoredCache] Fetched from DB: {len(paths)} paths")
        except Exception as e:
            logger.error(f"[IgnoredCache] DB fetch error: {e}")

        return paths

    async def add_ignored_path(self, path: str):
        """
        Add a path to the ignored cache.
        Called when a project is ignored.
        """
        try:
            # Add to Redis
            await redis_client.sadd(REDIS_KEY_IGNORED_PATHS, path)
            await redis_client.expire(REDIS_KEY_IGNORED_PATHS, CACHE_TTL)
            logger.info(f"[IgnoredCache] Added ignored path: {path}")
        except Exception as e:
            logger.warning(f"[IgnoredCache] Failed to add to cache: {e}")

    async def remove_ignored_path(self, path: str):
        """
        Remove a path from the ignored cache.
        Called when a project is un-ignored.
        """
        try:
            # Remove from Redis
            await redis_client.srem(REDIS_KEY_IGNORED_PATHS, path)
            logger.info(f"[IgnoredCache] Removed ignored path: {path}")
        except Exception as e:
            logger.warning(f"[IgnoredCache] Failed to remove from cache: {e}")

    async def invalidate_cache(self):
        """Invalidate the entire cache. Called when bulk operations occur."""
        try:
            await redis_client.delete(REDIS_KEY_IGNORED_PATHS)
            logger.info("[IgnoredCache] Cache invalidated")
        except Exception as e:
            logger.warning(f"[IgnoredCache] Failed to invalidate cache: {e}")

    async def is_ignored(self, path: str) -> bool:
        """
        Check if a specific path is ignored.
        Uses Redis SISMEMBER for O(1) lookup.
        """
        try:
            # Normalize path
            abs_path = path

            # Check exact match in Redis
            is_member = await redis_client.sismember(REDIS_KEY_IGNORED_PATHS, abs_path)
            if is_member:
                return True

            # Check if path is inside any ignored directory
            # This handles the case where we're checking a subpath
            ignored_paths = await self.get_ignored_paths()
            for ignored_path in ignored_paths:
                if abs_path.startswith(ignored_path + "/") or abs_path == ignored_path:
                    return True

            return False
        except Exception as e:
            logger.warning(f"[IgnoredCache] Error checking ignored status: {e}")
            # On error, fallback to DB check
            return await self._is_ignored_in_db(path)

    async def _is_ignored_in_db(self, path: str) -> bool:
        """Fallback DB check for ignored status."""
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(Repository).where(
                    Repository.local_path == path,
                    Repository.sync_status == "IGNORED"
                )
                result = await session.execute(stmt)
                return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(f"[IgnoredCache] DB fallback check error: {e}")
            return False


# Global instance
ignored_projects_cache = IgnoredProjectsCache()
