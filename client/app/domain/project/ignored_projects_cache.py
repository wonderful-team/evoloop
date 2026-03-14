"""
Ignored Projects Cache Manager

Manages caching of ignored project paths in memory for fast lookup
during tree generation and file operations.
"""

import asyncio
import logging
import time
from typing import Set, Optional

from sqlalchemy import select

from app.infrastructure.database.sql.database import AsyncSessionLocal
from app.models import Repository

logger = logging.getLogger(__name__)

# Cache TTL in seconds (10 minutes)
CACHE_TTL = 600


class IgnoredProjectsCache:
    """
    Cache manager for ignored project paths.

    Uses local memory cache with SQLite as backing store.
    Automatically refreshes cache on miss.
    """

    _instance = None
    _lock: Optional[asyncio.Lock] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache: Optional[Set[str]] = None
            cls._instance._cache_time: float = 0
            cls._lock = asyncio.Lock()
        return cls._instance

    async def get_ignored_paths(self, use_cache: bool = True) -> Set[str]:
        """
        Get set of ignored project paths.

        Args:
            use_cache: If True, try memory cache first; if False, always query DB

        Returns:
            Set of absolute paths of ignored projects
        """
        if use_cache:
            # Try memory cache first
            async with self._lock:
                if self._cache is not None and (time.time() - self._cache_time) < CACHE_TTL:
                    logger.debug(f"[IgnoredCache] Cache hit: {len(self._cache)} paths")
                    return self._cache.copy()

        # Cache miss or expired - fetch from DB
        return await self._fetch_from_db_and_refresh_cache()

    async def _fetch_from_db_and_refresh_cache(self) -> Set[str]:
        """Fetch ignored paths from DB and refresh memory cache."""
        paths = await self._fetch_from_db()

        # Update cache
        async with self._lock:
            self._cache = paths
            self._cache_time = time.time()
            logger.debug(f"[IgnoredCache] Cache refreshed: {len(paths)} paths")

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
        async with self._lock:
            if self._cache is None:
                self._cache = set()
            self._cache.add(path)
            self._cache_time = time.time()
            logger.info(f"[IgnoredCache] Added ignored path: {path}")

    async def remove_ignored_path(self, path: str):
        """
        Remove a path from the ignored cache.
        Called when a project is un-ignored.
        """
        async with self._lock:
            if self._cache is not None:
                self._cache.discard(path)
                self._cache_time = time.time()
            logger.info(f"[IgnoredCache] Removed ignored path: {path}")

    async def invalidate_cache(self):
        """Invalidate the entire cache. Called when bulk operations occur."""
        async with self._lock:
            self._cache = None
            self._cache_time = 0
            logger.info("[IgnoredCache] Cache invalidated")

    async def is_ignored(self, path: str) -> bool:
        """
        Check if a specific path is ignored.
        """
        try:
            # Normalize path
            abs_path = path

            # Check exact match and subpaths
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
