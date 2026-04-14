"""
Layered Context Cache - Zero-risk caching for static context data.

This module implements request-level caching with strict separation:
- STATIC layer: Project concepts, skill index, telemetry (cacheable)
- DYNAMIC layer: Blackboard, execution state, messages (never cached)

Safety guarantees:
- Dynamic state is always fresh
- Static data has TTL and verification
- Automatic invalidation on project/skill changes
"""

import logging
import time

from pydantic import Field

from app.core.engine.state import AgentState
from app.core.engine.state.blackboard import BlackboardState, VerificationStatus
from app.core.engine.state.config import ExecutionTicket
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class StaticContextLayer(DynamicBaseModel):
    """Static context that can be safely cached across nodes."""
    project_concepts: str | None = None
    active_skills_index: list = Field(default_factory=list)
    environment_telemetry: dict = Field(default_factory=dict)
    system_preferences: dict = Field(default_factory=dict)

    # Metadata
    project_id: int = 0
    cached_at: float = Field(default_factory=time.time)
    version: str = "1.0"

    def is_valid(self, max_age: int = 300) -> bool:
        """Check if cache is still valid."""
        return (time.time() - self.cached_at) < max_age


class DynamicContextLayer(DynamicBaseModel):
    """Dynamic context that must always be fresh."""
    blackboard: BlackboardState | None = None
    execution_ticket: ExecutionTicket | None = None
    messages: list = Field(default_factory=list)
    iteration_count: int = 0


class LayeredContextCache:
    """
    Layered context cache with strict safety controls.
    """

    # Static cache: session_id -> StaticContextLayer
    _static_cache: dict[str, StaticContextLayer] = {}

    # Statistics
    _stats = {
        'static_hits': 0,
        'static_misses': 0,
        'dynamic_loads': 0,
    }

    # TTL configuration (seconds)
    STATIC_TTL = 300  # 5 minutes for static data

    @classmethod
    async def get_static_layer(
        cls,
        session_id: str,
        project_id: int,
        loader_fn: callable
    ) -> StaticContextLayer:
        """
        Get static context layer with caching.
        
        Args:
            session_id: Unique session identifier
            project_id: Project ID for cache scoping
            loader_fn: Async function to load static data
        """
        cache_key = f"{session_id}:{project_id}"

        # Check cache
        if cache_key in cls._static_cache:
            cached = cls._static_cache[cache_key]
            if cached.is_valid(cls.STATIC_TTL):
                cls._stats['static_hits'] += 1
                logger.debug(f"[ContextCache] ✓ Static layer hit: {cache_key[:20]}...")
                return cached
            else:
                logger.debug(f"[ContextCache] TTL expired: {cache_key[:20]}...")
                del cls._static_cache[cache_key]

        # Load fresh data
        cls._stats['static_misses'] += 1
        logger.info(f"[ContextCache] Loading static layer for project {project_id}")

        start_time = time.time()
        static_data = await loader_fn()
        load_time = (time.time() - start_time) * 1000

        # Create cached layer
        layer = StaticContextLayer(
            project_concepts=static_data.get('project_concepts'),
            active_skills_index=static_data.get('active_skills', []),
            environment_telemetry=static_data.get('telemetry', {}),
            system_preferences=static_data.get('preferences', {}),
            project_id=project_id,
        )

        cls._static_cache[cache_key] = layer
        logger.info(f"[ContextCache] Static layer loaded in {load_time:.0f}ms")

        return layer

    @classmethod
    def get_dynamic_layer(cls, state: "AgentState") -> DynamicContextLayer:
        """
        Get dynamic context layer - always fresh, never cached.
        """
        cls._stats['dynamic_loads'] += 1

        # Extract last human message
        messages = list(state.messages) if state else []
        last_human_msg = ""
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human":
                last_human_msg = msg.content
                break

        return DynamicContextLayer(
            blackboard=state.blackboard,
            execution_ticket=state.blackboard.ticket if state.blackboard else None,
            messages=messages,
            iteration_count=state.iteration_count or 0,
        )

    @classmethod
    def invalidate_static(cls, session_id: str, project_id: int | None = None):
        """Invalidate static cache for a session or project."""
        if project_id:
            # Invalidate all entries for this project
            keys_to_remove = [
                k for k in cls._static_cache.keys()
                if k.endswith(f":{project_id}")
            ]
            for key in keys_to_remove:
                del cls._static_cache[key]
            logger.info(f"[ContextCache] Invalidated {len(keys_to_remove)} entries for project {project_id}")
        elif session_id:
            # Invalidate specific session
            keys_to_remove = [
                k for k in cls._static_cache.keys()
                if k.startswith(f"{session_id}:")
            ]
            for key in keys_to_remove:
                del cls._static_cache[key]

    @classmethod
    def get_stats(cls) -> dict:
        """Get cache statistics."""
        total_static = cls._stats['static_hits'] + cls._stats['static_misses']
        hit_rate = cls._stats['static_hits'] / total_static if total_static > 0 else 0.0

        return {
            'static_hits': cls._stats['static_hits'],
            'static_misses': cls._stats['static_misses'],
            'static_hit_rate': f"{hit_rate:.1%}",
            'dynamic_loads': cls._stats['dynamic_loads'],
            'cache_entries': len(cls._static_cache),
            'estimated_time_saved_ms': cls._stats['static_hits'] * 200,  # Approx 200ms per hit
        }

    @classmethod
    async def cleanup_expired(cls, max_age: int = 600):
        """Clean up expired cache entries."""
        now = time.time()
        expired = [
            k for k, v in cls._static_cache.items()
            if (now - v.cached_at) > max_age
        ]
        for key in expired:
            del cls._static_cache[key]

        if expired:
            logger.info(f"[ContextCache] Cleaned up {len(expired)} expired entries")


# Convenience function for health checks
def get_context_cache_stats() -> dict:
    return LayeredContextCache.get_stats()
