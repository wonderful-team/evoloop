"""Search backend factory for EvoLoop.

Provides a unified interface to switch between:
- SQLite FTS5 (embedded mode, local file)
- Meilisearch (production mode, external service)
"""

import logging
from typing import Optional

from app.core.config import settings
from app.infrastructure.search.base import SearchBackend

logger = logging.getLogger(__name__)

_search_backend: Optional[SearchBackend] = None


def get_search_backend() -> SearchBackend:
    """Get the global search backend instance (lazy singleton).

    Returns:
        SearchBackend: SQLiteFTSBackend or MeilisearchBackend.
    """
    global _search_backend
    if _search_backend is not None:
        return _search_backend

    engine = settings.SEARCH_ENGINE
    if engine == "auto":
        engine = "sqlite_fts" if settings.EMBEDDED_MODE else "meilisearch"

    if engine == "sqlite_fts":
        from app.infrastructure.search.sqlite_fts import SQLiteFTSBackend

        _search_backend = SQLiteFTSBackend()
        logger.info("[SearchBackend] Initialized SQLiteFTSBackend (embedded mode)")
    elif engine == "meilisearch":
        from app.infrastructure.search.meilisearch import MeilisearchBackend

        _search_backend = MeilisearchBackend()
        logger.info("[SearchBackend] Initialized MeilisearchBackend (production mode)")
    else:
        raise ValueError(f"Unknown SEARCH_ENGINE: {engine}")

    return _search_backend


def reset_search_backend() -> None:
    """Reset the global search backend instance (useful for testing)."""
    global _search_backend
    _search_backend = None
    logger.debug("[SearchBackend] Search backend reset")


__all__ = ["SearchBackend", "get_search_backend", "reset_search_backend"]
