"""RouteCatalog cache for the L0 routing layer.

This module is NOT a router. It builds and caches the enriched
:class:`RouteCatalog` that is returned by ``/route/init`` and used by BERT macro
resolution.  The spec contains the current macro templates, aliases, and voice
local actions.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.routing import constants as routing_constants
from app.core.routing.init_spec import build_and_enrich_spec
from app.core.routing.local_matcher import LocalMatcher
from app.core.routing.schemas import RouteCatalog
from app.infrastructure.cache import cache
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


async def _load_spec_from_cache() -> RouteCatalog | None:
    """Read the enriched RouteCatalog built by the Huey worker.

    Returns ``None`` when the cache is empty, unreadable, or holds an invalid
    payload. Callers should fall back to ``build_and_enrich_spec()``.
    """
    try:
        raw = await cache.get(routing_constants.SPEC_CACHE_KEY)
    except Exception:
        logger.warning("[matcher_cache] cache read failed", exc_info=True)
        return None

    if raw is None:
        return None

    try:
        if isinstance(raw, str):
            return RouteCatalog.model_validate_json(raw)
        return RouteCatalog.model_validate(raw)
    except Exception:
        logger.warning("[matcher_cache] failed to parse cached spec", exc_info=True)
        return None


async def build_and_cache_spec() -> RouteCatalog:
    """Build the spec from backend sources and mirror it into the cache.

    Shared by the API process (fallback/rebuild path) and the Huey worker
    (``tasks.build_l0_init_spec``); the cache write is best-effort.
    """
    spec = await build_and_enrich_spec()
    try:
        await cache.set(routing_constants.SPEC_CACHE_KEY, spec.model_dump_json())
    except Exception:
        logger.warning("[matcher_cache] cache write failed", exc_info=True)
    return spec


class RouteCatalogCache:
    """Build and cache the enriched :class:`RouteCatalog` used by L0 routing."""

    def __init__(self) -> None:
        self._spec: RouteCatalog | None = None
        self._matcher: LocalMatcher | None = None
        self._lock = asyncio.Lock()
        self._rebuild_lock = asyncio.Lock()
        self._rebuild_task: asyncio.Task | None = None


    async def diagnose(self, text: str, project_id: int | None = None) -> dict:
        """L0 miss triage: in-process matcher state vs shared cache vs live match."""
        cached_version = None
        cached_count = None
        cached = await _load_spec_from_cache()
        if cached is not None:
            cached_version = cached.version
            cached_count = len(cached.templates)
        in_proc_version = self._spec.version if self._spec else None
        in_proc_count = len(self._spec.templates) if self._spec else 0
        live_hit = None
        if self._matcher is not None:
            live_hit = self._matcher.match(text, project_id=project_id)
        return {
            "in_proc_version": in_proc_version,
            "in_proc_templates": in_proc_count,
            "shared_version": cached_version,
            "shared_templates": cached_count,
            "live_match": str(live_hit),
        }

    async def get_local_matcher(self) -> LocalMatcher | None:
        """Return a deterministic template matcher over the current spec.

        The matcher is rebuilt whenever the spec generation changes.  The
        in-process spec can drift from the shared cache (rebuilds happen in a
        debounced background task), so we reconcile against the shared cache
        version here: a stale in-process spec yields a stale matcher, which
        would silently miss freshly-created macros.  A spec with no templates
        yields ``None``.
        """
        await self.get()
        try:
            cached = await _load_spec_from_cache()
        except Exception:
            cached = None
        if (
            cached is not None
            and self._spec is not None
            and cached.version != self._spec.version
        ):
            self._spec = cached
            self._matcher = None
        if self._matcher is None and self._spec is not None and self._spec.templates:
            self._matcher = LocalMatcher(
                templates=self._spec.templates,
                slot_dictionaries=self._spec.slot_dictionaries,
                aliases=self._spec.aliases,
                app_usage_rank=self._spec.app_usage_rank,
                polite_prefixes=self._spec.polite_prefixes,
                polite_suffixes=self._spec.polite_suffixes,
                slot_filler_prefixes=self._spec.slot_filler_prefixes,
                slot_filler_suffixes=self._spec.slot_filler_suffixes,
                app_suffix_noise=self._spec.app_suffix_noise,
                free_text_reject_markers=self._spec.free_text_reject_markers,
                slot_filler_chars=self._spec.slot_filler_chars,
            )
        return self._matcher

    async def get(self) -> RouteCatalog:
        """Return the current spec, lazily building it on the first call.

        Reads are lock-free once a spec has been built.  Rebuild replaces the
        reference atomically, so concurrent callers always see either the old or
        the new spec, never a half-built one.

        The spec is read from the shared cache when available (populated by the
        Huey worker). If the cache is empty or unreadable we fall back to building
        from backend sources and writing the result back to the cache.
        """
        spec = self._spec
        if spec is not None:
            return spec

        async with self._lock:
            spec = await _load_spec_from_cache()
            source = "cache"
            if spec is None:
                spec = await build_and_cache_spec()
                source = "db"

            self._spec = spec
            self._matcher = None
            logger.debug("[route_catalog_cache] spec initialized from %s", source)
            return self._spec

    async def rebuild(self) -> None:
        """Rebuild the spec from sources and refresh the shared cache."""
        async with self._lock:
            self._spec = await build_and_cache_spec()
            self._matcher = None
        logger.debug("[route_catalog_cache] spec rebuilt")

    def invalidate(self) -> None:
        """Mark the in-process cached spec as stale so the next ``get()`` rebuilds it."""
        self._spec = None
        self._matcher = None
        logger.debug("[route_catalog_cache] in-process spec invalidated")

    async def invalidate_and_schedule_rebuild(
        self, delay: float = routing_constants.REBUILD_DEBOUNCE_SECONDS
    ) -> None:
        """Invalidate the in-process spec and schedule a debounced rebuild.

        Lifecycle events can arrive in bursts (e.g. macro CREATE + UPDATE + UPDATE,
        skill mutations, project switches).  Eagerly invalidating the in-process
        cache makes the next consumer aware that the spec is stale, while the
        debounced task coalesces the burst into a single shared-cache rebuild.
        """
        self.invalidate()
        async with self._rebuild_lock:
            if self._rebuild_task is not None and not self._rebuild_task.done():
                self._rebuild_task.cancel()
                try:
                    await self._rebuild_task
                except asyncio.CancelledError:
                    pass

            async def _rebuild_after_delay() -> None:
                try:
                    await asyncio.sleep(delay)
                    await self.rebuild()
                except asyncio.CancelledError:
                    pass

            self._rebuild_task = asyncio.create_task(_rebuild_after_delay())


# Module singleton.
matcher_cache = RouteCatalogCache()


async def _on_language_changed(_old_value: str, new_value: str) -> None:
    """LANGUAGE changes invalidate the spec and refresh the shared cache."""
    if not new_value:
        return

    # Lazy import to avoid a circular dependency at module load time.
    from app.core.routing.routing_data import get_store

    await get_store().reload(new_value)
    await matcher_cache.invalidate_and_schedule_rebuild()
    logger.info(
        "[route_catalog_cache] language changed to %s, spec invalidated", new_value
    )


try:
    SystemConfigService.register_change_handler("LANGUAGE", _on_language_changed)
except Exception:
    logger.debug(
        "[route_catalog_cache] failed to register LANGUAGE change handler",
        exc_info=True,
    )


__all__ = [
    "RouteCatalogCache",
    "build_and_cache_spec",
    "matcher_cache",
]
