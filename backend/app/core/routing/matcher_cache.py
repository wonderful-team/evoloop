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
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


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
        """
        matcher = self._matcher
        if matcher is not None:
            return matcher

        async with self._lock:
            if self._matcher is None:
                spec = await build_and_enrich_spec()
                self._matcher = LocalMatcher(
                    templates=spec.templates,
                    slot_dictionaries=spec.slot_dictionaries,
                    aliases=spec.aliases,
                    app_usage_rank=spec.app_usage_rank,
                )
                logger.debug("[matcher_cache] local matcher initialized")
            return self._matcher

    async def rebuild(self) -> None:
        """Rebuild the matcher (call after macro / language changes)."""
        async with self._lock:
            spec = await build_and_enrich_spec()
            self._matcher = LocalMatcher(
                templates=spec.templates,
                slot_dictionaries=spec.slot_dictionaries,
                aliases=spec.aliases,
                app_usage_rank=spec.app_usage_rank,
            )
        logger.debug("[matcher_cache] local matcher rebuilt")


# Module singleton.
matcher_cache = LocalMatcherCache()


async def _on_language_changed(_old_value: str, new_value: str) -> None:
    """LANGUAGE changes invalidate both the language store and the matcher cache."""
    if not new_value:
        return

    # Lazy import to avoid a circular dependency at module load time.
    from app.core.routing.routing_data import get_store

    await get_store().reload(new_value)
    await matcher_cache.rebuild()
    logger.info("[matcher_cache] language changed to %s, matcher rebuilt", new_value)


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
