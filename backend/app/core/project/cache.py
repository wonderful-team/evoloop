"""
Project domain cache utilities.

Simple cache operations for project-specific data.
Uses the global cache backend (Redis or FileCache).
"""

from app.constants import DEFAULT_PROJECT_ID
from app.core.project import constants as project_constants
from app.infrastructure.cache import cache


async def get_ignored_paths(project_id: int = DEFAULT_PROJECT_ID) -> set[str]:
    """Get all ignored paths for a project."""
    return await cache.smembers(_key(project_id, "ignored_paths"))


async def is_path_ignored(path: str, project_id: int = DEFAULT_PROJECT_ID) -> bool:
    """Check if a path is in the ignored list."""
    return await cache.sismember(_key(project_id, "ignored_paths"), path)


def _key(project_id: int, suffix: str) -> str:
    """Generate cache key."""
    return f"{project_constants.KEY_PREFIX}:{project_id}:{suffix}"
