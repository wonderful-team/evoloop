"""
Legacy FTS Service — thin wrapper around SearchBackend.

All logic has been moved to app.infrastructure.search.
This module remains for backward compatibility; new code should import
from app.infrastructure.search directly.
"""

import logging
from pathlib import Path
from typing import Optional

from app.infrastructure.search import get_search_backend
from app.infrastructure.search.base import (  # noqa: F401 — re-export for compat
    IndexDocumentRequest,
    KnowledgeSearchResult,
    ReindexResult,
    SearchIndexStats,
    SearchResults,
    SearchSuggestion,
)

logger = logging.getLogger(__name__)


class FTSService:
    """Deprecated: use app.infrastructure.search.get_search_backend() instead."""

    def __init__(self, db_path: Optional[Path] = None, pool=None):
        if db_path is not None:
            # Create an isolated backend for testing
            from app.infrastructure.search.sqlite_fts import SQLiteFTSBackend
            self._backend = SQLiteFTSBackend(db_path=db_path)
        else:
            self._backend = get_search_backend()
        # Expose pool for backward compat (only SQLiteFTSBackend has it)
        self.pool = getattr(self._backend, "pool", None)

    async def initialize(self) -> None:
        await self._backend.initialize()

    async def index_document(self, request: IndexDocumentRequest) -> bool:
        return await self._backend.index_document(request)

    async def remove_document(self, doc_id: str) -> bool:
        return await self._backend.remove_document(doc_id)

    async def search(
        self,
        query: str,
        collection: Optional[str] = None,
        tags: Optional[list[str]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResults:
        return await self._backend.search(query, collection, tags, limit, offset)

    async def suggest(
        self,
        prefix: str,
        collection: Optional[str] = None,
        limit: int = 10,
    ) -> list[SearchSuggestion]:
        return await self._backend.suggest(prefix, collection, limit)

    async def list_tags(
        self,
        collection: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[list[dict], int]:
        return await self._backend.list_tags(collection, limit)

    async def get_tag_config(self) -> list[dict]:
        return await self._backend.get_tag_config()

    async def update_tag_config(
        self,
        tag: str,
        category: str = "type",
        enabled: bool = True,
        priority: int = 0,
        description: str = "",
    ) -> bool:
        return await self._backend.update_tag_config(
            tag, category, enabled, priority, description
        )

    async def get_stats(self) -> SearchIndexStats:
        return await self._backend.get_stats()

    async def reindex_all(self, store_service) -> ReindexResult:
        return await self._backend.reindex_all(store_service)

    def close(self) -> None:
        self._backend.close()


# Singleton instance
_fts_service: Optional[FTSService] = None


def get_fts_service(db_path: Optional[Path] = None) -> FTSService:
    """Get or create FTS service singleton."""
    global _fts_service
    if _fts_service is None:
        _fts_service = FTSService(db_path=db_path)
    return _fts_service
