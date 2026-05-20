"""
Project domain cache utilities.

Simple cache operations for project-specific data.
Uses the global cache backend (Redis or FileCache).
"""

from app.infrastructure.cache import cache
from app.constants import DEFAULT_PROJECT_ID

KEY_PREFIX = "project"
DEFAULT_TTL = 3600  # 1 hour


async def get_ignored_paths(project_id: int = DEFAULT_PROJECT_ID) -> set[str]:
    """Get all ignored paths for a project."""
    return await cache.smembers(_key(project_id, "ignored_paths"))


async def add_ignored_path(path: str, project_id: int = DEFAULT_PROJECT_ID) -> bool:
    """Add a path to the ignored list."""
    key = _key(project_id, "ignored_paths")
    count = await cache.sadd(key, path)
    await cache.expire(key, DEFAULT_TTL)
    return count > 0


async def remove_ignored_path(path: str, project_id: int = DEFAULT_PROJECT_ID) -> bool:
    """Remove a path from the ignored list."""
    return await cache.srem(_key(project_id, "ignored_paths"), path) > 0


async def is_path_ignored(path: str, project_id: int = DEFAULT_PROJECT_ID) -> bool:
    """Check if a path is in the ignored list."""
    return await cache.sismember(_key(project_id, "ignored_paths"), path)


async def clear_ignored_paths(project_id: int = DEFAULT_PROJECT_ID) -> bool:
    """Clear all ignored paths for a project."""
    return await cache.delete(_key(project_id, "ignored_paths")) > 0


async def set_ignored_paths(paths: list[str], project_id: int = DEFAULT_PROJECT_ID) -> bool:
    """Replace all ignored paths for a project."""
    key = _key(project_id, "ignored_paths")
    pipe = cache.pipeline()
    pipe.delete(key)
    if paths:
        pipe.sadd(key, *paths)
        pipe.expire(key, DEFAULT_TTL)
    await pipe.execute()
    return True


def _key(project_id: int, suffix: str) -> str:
    """Generate cache key."""
    return f"{KEY_PREFIX}:{project_id}:{suffix}"
