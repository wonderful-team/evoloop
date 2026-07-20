"""Retriever: embed the utterance and fetch top-K route candidates."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from app.core.config import settings
from app.core.routing._errors import ROUTE_EXCEPTIONS
from app.core.routing.index import RouteIndex
from app.core.routing.schemas import RouteCandidate
from app.infrastructure.config import SystemConfigService

logger = logging.getLogger(__name__)

_DEFAULT_ROUTE_PATH = str(Path.home() / ".evoloop" / "vectors")
_INDEX: RouteIndex | None = None
_LOCK = threading.Lock()


def _cfg(key: str, default: str | None = None) -> str | None:
    try:
        return SystemConfigService.get_value(key, default)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError):
        return default


def get_index() -> RouteIndex:
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    with _LOCK:
        if _INDEX is None:
            path = (
                _cfg("LANCEDB_ROUTE_PATH", _DEFAULT_ROUTE_PATH) or _DEFAULT_ROUTE_PATH
            )
            dim_str = _cfg("EMBEDDING_DIMENSIONS")
            dim = (
                int(dim_str)
                if dim_str
                else int(getattr(settings, "EMBEDDING_DIMENSIONS", 768))
            )
            _INDEX = RouteIndex(path, dim=dim)
    return _INDEX


def _get_embedder():
    from app.infrastructure.embeddings.factory import EmbedderFactory

    model = _cfg("ROUTE_EMBEDDING_MODEL", "bge-base-zh-v1.5")
    embedder = EmbedderFactory.get_embedder(model)
    if embedder is not None:
        return embedder
    # No DB/system config: fall back to a dedicated LM Studio embedder so the
    # route works out-of-the-box (design §8.4 dedicated instance; §10.1 defaults
    # to lmstudio @ localhost:1234). Without this the router always sees zero
    # candidates and delegates everything on a fresh install.
    try:
        from app.infrastructure.embeddings.openai import GenericOpenAIEmbedder
    except ImportError:
        return None
    base = (
        _cfg("EMBEDDING_BASE_URL", "http://localhost:1234/v1")
        or "http://localhost:1234/v1"
    )
    try:
        dim = int(_cfg("EMBEDDING_DIMENSIONS", "768") or 768)
    except (TypeError, ValueError):
        dim = 768
    return GenericOpenAIEmbedder(
        api_key="lm-studio",
        base_url=base,
        model=model or "bge-base-zh-v1.5",
        dimensions=dim,
    )


def _dedupe_by_id(rows: list[dict]) -> list[dict]:
    """Keep the first (highest-scoring) row per id.

    The route index can hold duplicate ids when writes race (e.g. an
    incremental upsert overlapping a full rebuild); duplicates waste top-K
    slots and double-count a skill in the router prompt.
    """
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        rid = row.get("id")
        if rid in seen:
            continue
        seen.add(rid)
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# ASR partial transcript preheat cache (full-duplex streaming design §8.3)
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402

_preheat_cache: dict[str, list[RouteCandidate]] = {}
_preheat_lock = asyncio.Lock()

_PREHEAT_TTL_SECONDS = 10.0


async def preheat(thread_id: str, partial_text: str) -> None:
    """Pre-embed partial ASR transcript and cache candidates for faster routing.

    Called on voice.partial signals. The cached result is consumed by
    ``retrieve_cached()`` in ``_handle_route`` to skip re-embedding.
    """

    text = partial_text.strip()
    if len(text) < 2:
        return

    embedder = _get_embedder()
    if embedder is None:
        return

    try:
        vector = await embedder.embed_query(text)
        rows = get_index().search(vector, top_k=20)
        candidates = [RouteCandidate(**row) for row in _dedupe_by_id(rows)]
        async with _preheat_lock:
            _preheat_cache[thread_id] = candidates
        logger.debug(
            "[retriever] preheat for thread %s: %d candidates (text=%s)",
            thread_id,
            len(candidates),
            text[:40],
        )
    except ROUTE_EXCEPTIONS as exc:
        logger.debug("[retriever] preheat embed failed: %s", exc)


async def retrieve_cached(thread_id: str) -> list[RouteCandidate] | None:
    """Pop and return preheated candidates for thread_id, or None if no cache."""
    async with _preheat_lock:
        return _preheat_cache.pop(thread_id, None)


async def clear_preheat(thread_id: str) -> None:
    async with _preheat_lock:
        _preheat_cache.pop(thread_id, None)
