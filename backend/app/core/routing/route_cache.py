"""Route-decision cache (report §四十).

A route decision is a pure function of the self-contained (post-anaphora-
rewrite) text and the route-index version. Conservative by design:

- Exact normalized-text keys only — no semantic/fuzzy similarity (threshold
  overlap was rejected four times; it does not get revived inside a cache).
- Version-tagged keys: any route_index rebuild (macro/AppMap change) changes
  the LanceDB dataset version and invalidates all entries implicitly.
- Clarify decisions are session-dependent and never cached (callers simply
  return before the cache point).
- TTL + LRU bound as a safety net.

Toggle: ROUTE_CACHE_ENABLED=1 (default) | 0.
"""

from __future__ import annotations

import logging
import os
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.routing.schemas import RouteDecision

logger = logging.getLogger(__name__)

_TTL_SEC = 24 * 3600
_MAX_ENTRIES = 512
_PUNCT = "。，？！,.?!、 \t\r\n"

_store: OrderedDict[str, tuple[float, list[dict[str, Any]]]] = OrderedDict()
_hits = 0
_misses = 0


def enabled() -> bool:
    return os.environ.get("ROUTE_CACHE_ENABLED", "1").lower() not in ("0", "false", "off", "no")


def normalize(text: str) -> str:
    """Key normalization: trim + strip punctuation + lowercase (L0 parity)."""
    return text.strip().strip(_PUNCT).lower()


def route_index_version() -> str | None:
    """LanceDB dataset version + row count; None disables caching this call."""
    try:
        from app.core.routing.retriever import get_index

        table = get_index()._get_table()  # type: ignore[no-untyped-call]
        return f"{table.version}:{table.count_rows()}"
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        logger.debug("[route-cache] version unavailable: %s", exc)
        return None


async def key_for(text: str) -> str | None:
    version = route_index_version()
    if version is None:
        return None
    return f"{version}|{normalize(text)}"


def get(key: str | None) -> list[RouteDecision] | None:
    global _hits, _misses
    if key is None:
        return None
    from app.core.routing.schemas import RouteDecision

    entry = _store.get(key)
    if entry is None:
        _misses += 1
        return None
    expires, payload = entry
    if time.monotonic() > expires:
        del _store[key]
        _misses += 1
        return None
    _store.move_to_end(key)
    _hits += 1
    return [RouteDecision(**d) for d in payload]


def put(key: str | None, decisions: list[RouteDecision]) -> None:
    if key is None or not decisions:
        return
    payload = [d.model_dump() for d in decisions]
    _store[key] = (time.monotonic() + _TTL_SEC, payload)
    _store.move_to_end(key)
    while len(_store) > _MAX_ENTRIES:
        _store.popitem(last=False)


def stats() -> dict[str, int]:
    return {"hits": _hits, "misses": _misses, "entries": len(_store)}


def clear() -> None:
    global _hits, _misses
    _store.clear()
    _hits = _misses = 0
