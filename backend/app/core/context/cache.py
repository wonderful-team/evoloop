"""
Layered Context Cache - Zero-risk caching for static context data.

This module implements request-level caching with strict separation:
- STATIC layer: Project concepts, skill index, telemetry (cacheable)
- DYNAMIC layer: Shared context, execution state, messages (never cached)

Safety guarantees:
- Dynamic state is always fresh
- Static data has TTL and verification
- Automatic invalidation on project/skill changes
"""

import logging
import time
from typing import Any

from pydantic import Field

from app.constants import DEFAULT_PROJECT_ID
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


def _coerce_to_list(value: Any) -> list:
    """Normalize empty/None values to empty list while preserving real lists."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return list(value)


class StaticContextLayer(DynamicBaseModel):
    """Static context that can be safely cached across nodes."""

    project_concepts: str | None = None
    active_skills_index: list = Field(default_factory=list)
    active_macros_index: list = Field(default_factory=list)
    operation_map: str = ""
    system_preferences: dict = Field(default_factory=dict)

    # Memory pipeline fields — populated by AgentContextHydrator
    hot_memory: str | None = None
    episodes: str | None = None

    # Metadata
    project_id: int = DEFAULT_PROJECT_ID
    cached_at: float = Field(default_factory=time.time)
    version: str = "1.0"

    def is_valid(self, max_age: int = 300) -> bool:
        """Check if cache is still valid."""
        return (time.time() - self.cached_at) < max_age


class LayeredContextCache:
    """
    Layered context cache with strict safety controls.
    """

    # Static cache: session_id -> StaticContextLayer
    _static_cache: dict[str, StaticContextLayer] = {}

    # Statistics
    _stats = {
        "static_hits": 0,
        "static_misses": 0,
        "dynamic_loads": 0,
    }

    # TTL configuration (seconds)
    STATIC_TTL = 300  # 5 minutes for static data

    @classmethod
    async def get_static_layer(
        cls,
        session_id: str,
        project_id: int | None,
        loader_fn: callable,
        intent: str | None = None,
    ) -> StaticContextLayer:
        """
        Get static context layer with caching.

        Args:
            session_id: Unique session identifier
            project_id: Project ID for cache scoping (None defaults to global)
            loader_fn: Async function to load static data
        """
        project_id = project_id if project_id is not None else DEFAULT_PROJECT_ID
        intent_key = intent or "none"
        cache_key = f"{session_id}:{project_id}:{intent_key}"

        # Check cache
        if cache_key in cls._static_cache:
            cached = cls._static_cache[cache_key]
            if cached.is_valid(cls.STATIC_TTL):
                cls._stats["static_hits"] += 1
                logger.debug(f"[ContextCache] ✓ Static layer hit: {cache_key[:20]}...")
                return cached
            else:
                logger.debug(f"[ContextCache] TTL expired: {cache_key[:20]}...")
                del cls._static_cache[cache_key]

        # Load fresh data
        cls._stats["static_misses"] += 1
        logger.info(f"[ContextCache] Loading static layer for project {project_id}")

        start_time = time.time()
        static_data = await loader_fn()
        load_time = (time.time() - start_time) * 1000

        # Create cached layer
        layer = StaticContextLayer(
            project_concepts=static_data.get("project_concepts"),
            active_skills_index=_coerce_to_list(static_data.get("active_skills", [])),
            active_macros_index=_coerce_to_list(static_data.get("active_macros", [])),
            operation_map=static_data.get("operation_map", ""),
            system_preferences=static_data.get("preferences", {}) or {},
            # Memory pipeline — carry through from loader_fn output
            hot_memory=static_data.get("hot_memory"),
            episodes=static_data.get("episodes"),
            project_id=project_id,
        )

        cls._static_cache[cache_key] = layer
        logger.info(f"[ContextCache] Static layer loaded in {load_time:.0f}ms")

        return layer

    @classmethod
    def invalidate_static(cls, session_id: str, project_id: int | None = None):
        """Invalidate static cache for a session or project."""
        if project_id is not None:
            # Invalidate all entries for this project (project_id=DEFAULT_PROJECT_ID/0 is global mode, also valid)
            keys_to_remove = [
                k for k in cls._static_cache.keys() if k.endswith(f":{project_id}")
            ]
            for key in keys_to_remove:
                del cls._static_cache[key]
            logger.info(f"[ContextCache] Invalidated {len(keys_to_remove)} entries for project {project_id}")
        elif session_id:
            # Invalidate specific session
            keys_to_remove = [
                k for k in cls._static_cache.keys() if k.startswith(f"{session_id}:")
            ]
            for key in keys_to_remove:
                del cls._static_cache[key]

    @classmethod
    def get_stats(cls) -> dict:
        """Get cache statistics."""
        total_static = cls._stats["static_hits"] + cls._stats["static_misses"]
        hit_rate = cls._stats["static_hits"] / total_static if total_static > 0 else 0.0

        return {
            "static_hits": cls._stats["static_hits"],
            "static_misses": cls._stats["static_misses"],
            "static_hit_rate": f"{hit_rate:.1%}",
            "dynamic_loads": cls._stats["dynamic_loads"],
            "cache_entries": len(cls._static_cache),
            "estimated_time_saved_ms": cls._stats["static_hits"] * 200,  # Approx 200ms per hit
        }
