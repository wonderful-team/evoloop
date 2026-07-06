import logging
import time
from typing import Protocol

from app.core.context.manager import EvoContext

logger = logging.getLogger(__name__)
# Detailed hydration logging - set to True for debugging hydration issues
_LOG_HYDRATION_DETAILS = False


class ContextPlugin(Protocol):
    """
    Protocol for context plugins.
    Domain modules should implement this to inject their specific
    state/knowledge into the generic EvoContext.
    """

    def hydrate(self, ctx: EvoContext) -> None:
        """Inject domain-specific knowledge into the context"""
        ...


class ContextPluginRegistry:
    """
    Registry for all context plugins.
    
    Optimization:
    - Caches hydration results with 5s TTL to avoid redundant plugin execution
      across multiple prompt builders in the same request.
    """

    def __init__(self):
        self._plugins: list[ContextPlugin] = []
        # Cache for hydration results: (thread_id, project_id) -> (result, timestamp)
        self._hydration_cache: dict[tuple[str, int], tuple[dict, float]] = {}
        self._cache_ttl: float = 10.0  # 10 seconds TTL (increased from 5s)
        # Cache statistics for monitoring
        self._stats = {"hits": 0, "misses": 0, "expired": 0}

    def register(self, plugin: ContextPlugin) -> None:
        self._plugins.append(plugin)
        logger.debug(f"Registered ContextPlugin: {plugin.__class__.__name__}")

    def hydrate_context(self, ctx: EvoContext) -> None:
        """
        Run all registered plugins to populate the given context.
        Uses caching to avoid redundant execution within the same request.
        
        Optimization:
        - Uses stable cache key (fallback to request_id if thread_id is None)
        - Reduced logging frequency for production
        - 10s TTL to reduce redundant hydration during fast agent execution
        """
        # Generate stable cache key - use request_id as fallback for thread_id
        # to avoid all None-thread_id contexts sharing one cache entry
        effective_thread_id = ctx.thread_id or ctx.request_id or "global"
        from app.constants import DEFAULT_PROJECT_ID
        cache_key = (effective_thread_id, ctx.project_id if ctx.project_id is not None else DEFAULT_PROJECT_ID)
        now = time.time()

        # Check cache
        if cache_key in self._hydration_cache:
            cached_result, cached_time = self._hydration_cache[cache_key]
            if now - cached_time < self._cache_ttl:
                # Cache hit: Apply cached values
                self._stats["hits"] += 1
                if _LOG_HYDRATION_DETAILS:
                    logger.debug(f"[PluginRegistry] Cache hit for {cache_key}")
                if "environment_block" in cached_result:
                    ctx.environment_block = cached_result["environment_block"]
                return
            else:
                # Cache expired
                self._stats["expired"] += 1
                if _LOG_HYDRATION_DETAILS:
                    logger.debug(f"[PluginRegistry] Cache expired for {cache_key}")
                del self._hydration_cache[cache_key]

        # Cache miss: Run all plugins
        self._stats["misses"] += 1
        if _LOG_HYDRATION_DETAILS:
            logger.debug(f"[PluginRegistry] Cache miss, hydrating {len(self._plugins)} plugins")

        for plugin in self._plugins:
            try:
                plugin.hydrate(ctx)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.error(f"Error executing ContextPlugin {plugin.__class__.__name__}: {e}")

        # Cache the result
        self._hydration_cache[cache_key] = (
            {"environment_block": ctx.environment_block},
            now
        )

        # Cleanup old cache entries (simple LRU)
        if len(self._hydration_cache) > 100:
            oldest_key = min(self._hydration_cache.keys(),
                           key=lambda k: self._hydration_cache[k][1])
            del self._hydration_cache[oldest_key]

    def get_stats(self) -> dict:
        """Get cache statistics for monitoring."""
        total = self._stats["hits"] + self._stats["misses"] + self._stats["expired"]
        hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0
        return {
            **self._stats,
            "total_requests": total,
            "hit_rate": f"{hit_rate:.1f}%",
            "cache_size": len(self._hydration_cache),
        }

    def reset_stats(self) -> None:
        """Reset cache statistics."""
        self._stats = {"hits": 0, "misses": 0, "expired": 0}


# Global registry instance
plugin_registry = ContextPluginRegistry()


class WorkspaceProvider(Protocol):
    """
    Protocol for providing workspace-level context, such as project file structure.
    Normally implemented by the domain layer (e.g., app.core.project).
    """
    async def get_project_structure(self, path: str) -> str:
        """Returns a string representation of the project structure at the given path."""
        ...


_workspace_provider: WorkspaceProvider | None = None


def set_workspace_provider(provider: WorkspaceProvider):
    """Register the global WorkspaceProvider."""
    global _workspace_provider
    _workspace_provider = provider


def get_workspace_provider() -> WorkspaceProvider | None:
    """Retrieve the global WorkspaceProvider."""
    return _workspace_provider
