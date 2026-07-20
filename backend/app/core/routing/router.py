"""Local matcher factory — L0 fast path for voice channel."""

from __future__ import annotations

import asyncio
import logging

from app.core.routing import init_spec
from app.core.routing.local_matcher import LocalMatcher

logger = logging.getLogger(__name__)

_LOCAL_MATCHER: LocalMatcher | None = None
_LOCAL_MATCHER_LOCK = asyncio.Lock()


async def _get_local_matcher() -> LocalMatcher:
    """Lazily build the deterministic Layer-0 matcher used by the client."""
    global _LOCAL_MATCHER
    if _LOCAL_MATCHER is not None:
        return _LOCAL_MATCHER
    async with _LOCAL_MATCHER_LOCK:
        if _LOCAL_MATCHER is not None:
            return _LOCAL_MATCHER
        spec = await asyncio.to_thread(init_spec.build_init_spec)
        _LOCAL_MATCHER = LocalMatcher(
            templates=spec.templates,
            slot_dictionaries=spec.slot_dictionaries,
            aliases=spec.aliases,
            app_usage_rank=spec.app_usage_rank,
        )
        logger.debug("[router] local matcher initialized")
    return _LOCAL_MATCHER
