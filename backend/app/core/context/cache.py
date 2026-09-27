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
from app.core.context import constants as context_constants
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.time import elapsed_ms

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

    # Static cache: thread_id -> StaticContextLayer
    _static_cache: dict[str, StaticContextLayer] = {}

    MAX_STATIC_ENTRIES = 256

    # Statistics
    _stats = {
        "static_hits": 0,
        "static_misses": 0,
        "dynamic_loads": 0,
    }

    @classmethod
    async def get_static_layer(
        cls,
        session_id: str,
        project_id: int | None,
        loader_fn: callable,
        intent: str | None = None,
        explicit_key: str | None = None,
    ) -> StaticContextLayer:
        """
        Get static context layer with caching.

        Args:
            session_id: Unique session identifier
            project_id: Project ID for cache scoping (None defaults to global)
            loader_fn: Async function to load static data
            intent: Intent hint for telescopic gating
            explicit_key: Signature of explicitly requested skills (skill_ids), so
                different explicit-skill selections don't collide in the cache.
        """
        project_id = project_id if project_id is not None else DEFAULT_PROJECT_ID
        intent_key = intent or "none"
        cache_key = f"{session_id}:{project_id}:{intent_key}:{explicit_key or ''}"

        # Check cache
        if cache_key in cls._static_cache:
            cached = cls._static_cache[cache_key]
            if cached.is_valid(context_constants.STATIC_TTL):
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
        load_time = elapsed_ms(start_time)

        # Create cached layer
        layer = StaticContextLayer(
            project_concepts=static_data.get("project_concepts"),
            active_skills_index=_coerce_to_list(static_data.get("active_skills", [])),
            active_macros_index=_coerce_to_list(static_data.get("active_macros", [])),
            system_preferences=static_data.get("preferences", {}) or {},
            # Memory pipeline — carry through from loader_fn output
            hot_memory=static_data.get("hot_memory"),
            episodes=static_data.get("episodes"),
            project_id=project_id,
        )

        # 泄漏护栏：thread 级键仍随 thread 数缓增（TTL 惰性清除只在重读时
        # 发生）。超过上限时主动清理过期项，保底丢弃最旧条目。
        if len(cls._static_cache) >= cls.MAX_STATIC_ENTRIES:
            expired = [
                k
                for k, v in cls._static_cache.items()
                if not v.is_valid(context_constants.STATIC_TTL)
            ]
            for k in expired:
                del cls._static_cache[k]
            if len(cls._static_cache) >= cls.MAX_STATIC_ENTRIES:
                oldest = min(cls._static_cache.items(), key=lambda kv: kv[1].cached_at)
                del cls._static_cache[oldest[0]]
        cls._static_cache[cache_key] = layer
        logger.info(f"[ContextCache] Static layer loaded in {load_time:.0f}ms")

        return layer

    @classmethod
    def invalidate_static(cls, session_id: str | None, project_id: int | None = None):
        """Invalidate static cache for a session or project.

        两者皆 None → 全部清空（技能是全局资源，reload 后所有 thread
        的 <available_skills> 索引应立即可见）。
        """
        if project_id is None and session_id is None:
            count = len(cls._static_cache)
            cls._static_cache.clear()
            logger.info(f"[ContextCache] Invalidated all {count} static layer entries")
            return
        if project_id is not None:
            # Invalidate all entries for this project (project_id=DEFAULT_PROJECT_ID/0 is global mode, also valid)
            # 审计修复：键格式 {session}:{project}:{intent}:{explicit}，
            # endswith(f":{project_id}") 永远匹配尾段（explicit_key）——
            # 结构性失配。改为按第二段精确匹配。
            keys_to_remove = [
                k
                for k in cls._static_cache.keys()
                if len(k.split(":")) > 1 and k.split(":")[1] == str(project_id)
            ]
            for key in keys_to_remove:
                del cls._static_cache[key]
            logger.info(
                f"[ContextCache] Invalidated {len(keys_to_remove)} entries for project {project_id}"
            )
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
            "estimated_time_saved_ms": cls._stats["static_hits"]
            * 200,  # Approx 200ms per hit
        }
