"""
SearchBackend — Abstract protocol for full-text search.

Implementations:
- SQLiteFTSBackend (embedded mode, local SQLite FTS5)
- MeilisearchBackend (production mode, external Meilisearch service)

Usage:
    from app.infrastructure.search import get_search_backend
    search = get_search_backend()
    await search.index_document(...)
    results = await search.search("query", limit=20)
"""

from typing import Any, Optional, Protocol, runtime_checkable

from app.infrastructure.schemas import SearchResults, SearchSuggestion, SearchIndexStats, ReindexResult, \
    IndexDocumentRequest, KnowledgeSearchResult


# ---------------------------------------------------------------------------
# Shared models (previously in domain/knowledge/services/search.py)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SearchBackend(Protocol):
    """Protocol defining the unified full-text search interface."""

    async def initialize(self) -> None:
        """Ensure search index/tables exist."""
        ...

    async def index_document(self, request: IndexDocumentRequest) -> bool:
        """Index or update a document."""
        ...

    async def remove_document(self, doc_id: str) -> bool:
        """Remove a document from the index."""
        ...

    async def search(
        self,
        query: str,
        collection: Optional[str] = None,
        tags: Optional[list[str]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResults:
        """Full-text search with optional filters."""
        ...

    async def suggest(
        self,
        prefix: str,
        collection: Optional[str] = None,
        limit: int = 10,
    ) -> list[SearchSuggestion]:
        """Search suggestions based on prefix."""
        ...

    async def list_tags(
        self,
        collection: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[list[dict], int]:
        """List tags with document counts."""
        ...

    async def get_tag_config(self) -> list[dict]:
        """Load enabled tag configuration."""
        ...

    async def update_tag_config(
        self,
        tag: str,
        category: str = "type",
        enabled: bool = True,
        priority: int = 0,
        description: str = "",
    ) -> bool:
        """Upsert a tag configuration entry."""
        ...

    async def get_stats(self) -> SearchIndexStats:
        """Get search index statistics."""
        ...

    async def reindex_all(self, store_service: Any) -> ReindexResult:
        """Reindex all documents from storage."""
        ...

    def close(self) -> None:
        """Release any underlying resources."""
        ...
