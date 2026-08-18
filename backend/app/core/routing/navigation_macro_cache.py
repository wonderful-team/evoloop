"""In-memory cache for preset navigation macros.

Navigation macros are DB ``Macro`` records whose script contains a single
``frontend_navigate`` step.  They are matched by exact trigger phrase before
BERT classification, replacing the previous ``nav_routes.yaml`` fast path.

The cache is lazy (no DB query at import time) and TTL-based so that runtime
changes to preset navigation macros are picked up without an application restart.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NavigationMacroInfo:
    """Lightweight handle for a cached navigation macro."""

    id: int
    route: str
    feedback: str
    phrase: str


class NavigationMacroCache:
    """Exact-phrase cache for preset navigation macros.

    Args:
        ttl_seconds: How long the cache stays fresh before re-querying DB.
    """

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()
        self._cache: dict[str, NavigationMacroInfo] | None = None
        self._last_refresh: float = 0.0
        self._refreshing = False

    async def get(self, phrase: str) -> NavigationMacroInfo | None:
        """Return the navigation macro matching ``phrase``.

        Returns ``None`` when no macro matches or the DB is unreachable.
        """
        await self._maybe_refresh()
        return self._cache.get(phrase) if self._cache is not None else None

    async def refresh(self) -> None:
        """Force a refresh of the cache."""
        async with self._lock:
            self._last_refresh = 0.0
        await self._maybe_refresh()

    async def _maybe_refresh(self) -> None:
        now = time.monotonic()
        if now - self._last_refresh < self._ttl and self._cache is not None:
            return

        # Only one refresher at a time.
        async with self._lock:
            if self._refreshing:
                return
            self._refreshing = True

        try:
            data = await self._load()
            async with self._lock:
                self._cache = data
                self._last_refresh = time.monotonic()
        except Exception:
            logger.exception("[nav_macro_cache] failed to load navigation macros")
        finally:
            async with self._lock:
                self._refreshing = False

    async def _load(self) -> dict[str, NavigationMacroInfo]:
        """Query DB for active preset navigation macros."""
        from app.core.execution.macro import list_macros

        macros = await list_macros(status="verified", is_active=True, namespace="preset")
        macros.sort(key=lambda m: m.id)

        data: dict[str, NavigationMacroInfo] = {}
        for macro in macros:
            from app.core.execution.macro import is_navigation_macro

            route = is_navigation_macro(macro)
            if route is None:
                continue
            feedback = macro.feedback or ""
            for pattern in macro.trigger_patterns or []:
                if isinstance(pattern, str) and pattern:
                    data[pattern] = NavigationMacroInfo(
                        id=macro.id,
                        route=route,
                        feedback=feedback,
                        phrase=pattern,
                    )
        return data


# Module singleton used by CommandRouter.
_navigation_macro_cache: NavigationMacroCache | None = None


def get_navigation_macro_cache() -> NavigationMacroCache:
    """Return the module singleton ``NavigationMacroCache``."""
    global _navigation_macro_cache
    if _navigation_macro_cache is None:
        _navigation_macro_cache = NavigationMacroCache()
    return _navigation_macro_cache


__all__ = [
    "NavigationMacroCache",
    "NavigationMacroInfo",
    "get_navigation_macro_cache",
]
