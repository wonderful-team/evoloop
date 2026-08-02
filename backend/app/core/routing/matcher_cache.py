"""Local matcher cache for the L0 routing layer.

This module is NOT a router. It builds and caches the deterministic
:class:`LocalMatcher` compiled from the enriched :class:`RouteCatalog`.  The
matcher is used by :class:`app.core.routing.command_router.CommandRouter` for
server-side fallback matching and by clients via the serialized RouteCatalog.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.routing.init_spec import build_and_enrich_spec
from app.core.routing.local_matcher import LocalMatcher
from app.core.routing.schemas import RouteCatalog
from app.infrastructure.cache import cache
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)

SPEC_CACHE_KEY = "l0:init_spec:current"


def _matcher_from_spec(spec: RouteCatalog) -> LocalMatcher:
    """Build a LocalMatcher from an enriched RouteCatalog."""
    return LocalMatcher(
        templates=spec.templates,
        slot_dictionaries=spec.slot_dictionaries,
        aliases=spec.aliases,
        app_usage_rank=spec.app_usage_rank,
    )


async def _load_spec_from_cache() -> RouteCatalog | None:
    """Read the enriched RouteCatalog built by the Huey worker.

    Returns ``None`` when the cache is empty, unreadable, or holds an invalid
    payload. Callers should fall back to ``build_and_enrich_spec()``.
    """
    try:
        raw = await cache.get(SPEC_CACHE_KEY)
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


async def _build_and_cache_spec() -> RouteCatalog:
    """Build the spec from backend sources and mirror it into the cache."""
    spec = await build_and_enrich_spec()
    try:
        await cache.set(SPEC_CACHE_KEY, spec.model_dump_json())
    except Exception:
        logger.warning("[matcher_cache] cache write failed", exc_info=True)
    return spec


class LocalMatcherCache:
    """Build and cache the :class:`LocalMatcher` used by L0 routing."""

    def __init__(self) -> None:
        self._matcher: LocalMatcher | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> LocalMatcher:
        """Return the current matcher, lazily building it on the first call.

        Reads are lock-free once a matcher has been built.  Rebuild replaces the
        reference atomically, so concurrent callers always see either the old or
        the new matcher, never a half-built one.

        The matcher is built from the shared RouteCatalog cache when available
        (populated by the Huey worker). If the cache is empty or unreadable we
        fall back to building from backend sources and writing the result back
        to the cache.
        """
        matcher = self._matcher
        if matcher is not None:
            return matcher

        async with self._lock:
            if self._matcher is not None:
                return self._matcher

            spec = await _load_spec_from_cache()
            source = "cache"
            if spec is None:
                spec = await _build_and_cache_spec()
                source = "db"

            self._matcher = _matcher_from_spec(spec)
            logger.debug("[matcher_cache] local matcher initialized from %s", source)
            return self._matcher

    async def rebuild(self) -> None:
        """Rebuild the matcher from sources and refresh the shared cache."""
        async with self._lock:
            spec = await _build_and_cache_spec()
            self._matcher = _matcher_from_spec(spec)
        logger.debug("[matcher_cache] local matcher rebuilt")

    def invalidate(self) -> None:
        """Mark the cached matcher as stale so the next ``get()`` rebuilds it."""
        self._matcher = None
        logger.debug("[matcher_cache] local matcher invalidated")

    def invalidate_and_schedule_rebuild(self) -> None:
        """Invalidate the local matcher and dispatch a background Huey task to rebuild the shared RouteCatalog."""
        self.invalidate()
        try:
            from app.core.routing.tasks import build_l0_init_spec
            build_l0_init_spec.delay()
        except Exception:
            logger.warning("[matcher_cache] failed to dispatch L0 init spec rebuild", exc_info=True)


# Module singleton.
matcher_cache = LocalMatcherCache()


async def _on_language_changed(_old_value: str, new_value: str) -> None:
    """LANGUAGE changes invalidate the local matcher and refresh the shared cache."""
    if not new_value:
        return

    # Lazy import to avoid a circular dependency at module load time.
    from app.core.routing.routing_data import get_store

    await get_store().reload(new_value)
    matcher_cache.invalidate_and_schedule_rebuild()
    logger.info("[matcher_cache] language changed to %s, matcher invalidated", new_value)


try:
    SystemConfigService.register_change_handler("LANGUAGE", _on_language_changed)
except Exception:
    logger.debug(
        "[matcher_cache] failed to register LANGUAGE change handler",
        exc_info=True,
    )


__all__ = [
    "LocalMatcherCache",
    "matcher_cache",
]
