import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_search_backend = None


def get_search_backend():
    global _search_backend
    if _search_backend is not None:
        return _search_backend

    engine = settings.SEARCH_ENGINE
    if engine == "auto":
        engine = "sqlite_fts" if settings.EMBEDDED_MODE else "meilisearch"

    if engine == "sqlite_fts":
        from app.infrastructure.search.sqlite_fts import SQLiteFTSBackend
        _search_backend = SQLiteFTSBackend()
    elif engine == "meilisearch":
        from app.infrastructure.search.meilisearch import MeilisearchBackend
        _search_backend = MeilisearchBackend()
    else:
        raise ValueError(f"Unknown search engine: {engine}")

    return _search_backend