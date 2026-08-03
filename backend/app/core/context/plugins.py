import asyncio
import logging
import time
from typing import Any, Protocol

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import EvoContext

logger = logging.getLogger(__name__)


class ContextPlugin(Protocol):
    """
    Protocol for context plugins.
    Domain modules implement this to inject their specific state/knowledge into
    the generic EvoContext.

    Plugins may gate themselves by intent via ``is_needed``. The default returns
    ``True`` so plugins without an intent preference still hydrate every request.
    """

    def is_needed(self, intent: str | None) -> bool:
        """Return True when this plugin should hydrate for the given intent."""
        return True

    def hydrate(self, ctx: EvoContext) -> None:
        """Inject domain-specific knowledge into the context"""
        ...


class ContextPluginRegistry:
    """
    Registry for all context plugins.

    Optimization:
    - Caches hydration results with a short TTL to avoid redundant plugin execution
      across multiple prompt builders in the same request.
    - Resets gated fields before running plugins so that skipped plugins do not leave
      stale data in the context (e.g. environment summaries for a direct_answer intent).
    """

    # Fields that are populated by plugins and must be reset/restored atomically.
    _CTX_FIELDS = frozenset({
        "environment_block",
        "environment_summaries",
        "active_boundaries",
        "memory_replay",
        "spatial_awareness",
        "wiki_index",
    })
    _META_FIELDS = frozenset({
        "has_android",
        "has_macos",
        "user_preferences",
        "active_plan_context",
    })

    def __init__(self):
        self._plugins: list[ContextPlugin] = []
        # Cache for hydration results: (thread_id, project_id, intent) -> (result, timestamp)
        self._hydration_cache: dict[tuple[str, int, str], tuple[dict, float]] = {}
        self._cache_ttl: float = 10.0  # 10 seconds TTL
        # Cache statistics for monitoring
        self._stats = {"hits": 0, "misses": 0, "expired": 0}

    def register(self, plugin: ContextPlugin) -> None:
        self._plugins.append(plugin)
        logger.debug(f"Registered ContextPlugin: {plugin.__class__.__name__}")

    def _reset_hydrated_fields(self, ctx: EvoContext) -> None:
        """Clear fields that are gated by plugins to avoid stale data."""
        ctx.environment_block = None
        ctx.environment_summaries = {}
        ctx.active_boundaries = []
        ctx.memory_replay = {}
        ctx.spatial_awareness = {}
        ctx.wiki_index = []
        for field in self._META_FIELDS:
            if field in ("has_android", "has_macos"):
                setattr(ctx.metadata, field, False)
            else:
                setattr(ctx.metadata, field, None)

    def _snapshot_hydrated_fields(self, ctx: EvoContext) -> dict[str, Any]:
        """Capture the state of all plugin-populated fields."""
        meta = {
            field: getattr(ctx.metadata, field, None) for field in self._META_FIELDS
        }
        return {
            **{field: getattr(ctx, field, None) for field in self._CTX_FIELDS},
            "metadata": meta,
        }

    def _apply_snapshot(self, ctx: EvoContext, snapshot: dict[str, Any]) -> None:
        """Restore plugin-populated fields from a cache snapshot."""
        for field in self._CTX_FIELDS:
            if field in snapshot:
                setattr(ctx, field, snapshot[field])
        meta = snapshot.get("metadata", {})
        for field in self._META_FIELDS:
            if field in meta:
                setattr(ctx.metadata, field, meta[field])

    def hydrate_context(self, ctx: EvoContext, intent: str | None = None) -> None:
        """
        Run registered plugins to populate the given context.

        Plugins that implement ``is_needed(intent)`` and return ``False`` are
        skipped, allowing expensive context providers to stay dormant when the
        current intent does not require their data.  Skipped plugins still have
        their fields cleared before/after the run so that stale data does not
        leak into intents that should not see it.

        Args:
            ctx: The context to hydrate.
            intent: Optional high-level intent string from the L0 classifier.
                When ``None``, the classifier-written ``intent_hint`` on
                ``ctx.metadata`` is used as a fallback so that downstream
                calls from ``SupervisorPromptBuilder`` / ``WorkerPromptBuilder``
                land on the same cache bucket as the initial
                ``AgentContextHydrator.hydrate()`` call rather than overwriting
                intent-gated state with a fresh "none" bucket run (which would
                undo the telescopic context selection done upstream).
        """
        # Resolve effective intent: explicit arg takes precedence, otherwise
        # fall back to whatever the L0 classifier wrote onto the context. This
        # keeps repeated ahydrate_context(ctx) calls cache-consistent with the
        # hydrator's intent-keyed run; otherwise the supervisor / worker
        # prompt builders' second call would land in the "none" bucket and
        # re-populate Environment / Project state that the intent had skipped.
        effective_intent = intent
        if effective_intent is None:
            hint = getattr(ctx.metadata, "get", lambda *_: None)("intent_hint")
            if isinstance(hint, dict):
                effective_intent = hint.get("intent")

        # Generate stable cache key - use request_id as fallback for thread_id
        # to avoid all None-thread_id contexts sharing one cache entry
        effective_thread_id = ctx.thread_id or ctx.request_id or "global"
        cache_key = (
            effective_thread_id,
            ctx.project_id if ctx.project_id is not None else DEFAULT_PROJECT_ID,
            effective_intent or "none",
        )
        now = time.time()

        # Check cache
        if cache_key in self._hydration_cache:
            cached_result, cached_time = self._hydration_cache[cache_key]
            if now - cached_time < self._cache_ttl:
                # Cache hit: restore the full snapshot and skip plugin execution.
                self._stats["hits"] += 1
                self._apply_snapshot(ctx, cached_result)
                return
            else:
                # Cache expired
                self._stats["expired"] += 1
                del self._hydration_cache[cache_key]

        # Cache miss: reset gated fields, then run all needed plugins.
        self._stats["misses"] += 1
        self._reset_hydrated_fields(ctx)

        for plugin in self._plugins:
            if not plugin.is_needed(effective_intent):
                continue
            try:
                plugin.hydrate(ctx)
            except Exception:
                logger.exception("Error executing ContextPlugin %s", plugin.__class__.__name__)

        # Cache the full snapshot of plugin-written fields.
        self._hydration_cache[cache_key] = (
            self._snapshot_hydrated_fields(ctx),
            now,
        )

        # Cleanup old cache entries (simple LRU)
        if len(self._hydration_cache) > 100:
            oldest_key = min(self._hydration_cache.keys(), key=lambda k: self._hydration_cache[k][1])
            del self._hydration_cache[oldest_key]

    async def ahydrate_context(self, ctx: EvoContext, intent: str | None = None) -> None:
        """
        Async wrapper that runs the synchronous plugin chain in a worker thread.

        Plugins may perform blocking I/O (e.g. synchronous DB sessions), so the
        registry must not execute them on the event loop thread.
        """
        await asyncio.to_thread(self.hydrate_context, ctx, intent=intent)


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
