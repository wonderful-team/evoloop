"""
BaseVectorStore — Abstract protocol for vector storage backends.

Implementations:
- LanceVectorStore (embedded mode, local file-based)
- PgVectorStore (production mode, PostgreSQL + pgvector)

All methods are synchronous. Implementations that wrap async libraries
are responsible for internal event-loop management.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BaseVectorStore(Protocol):
    """Protocol defining the unified vector store interface."""

    # ------------------------------------------------------------------
    # Code embeddings
    # ------------------------------------------------------------------
    def upsert_code_chunks(
        self,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> int:
        """Upsert code chunks with embeddings. Returns count inserted."""
        ...

    def search_code(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: str | None = None,
        repository_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over code chunks."""
        ...

    def full_text_search_code(
        self,
        query_text: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Full-text search on code content."""
        ...

    def delete_by_repository(self, repository_id: str) -> int:
        """Delete all chunks for a repository."""
        ...

    # ------------------------------------------------------------------
    # Knowledge-base / document embeddings
    # ------------------------------------------------------------------
    def upsert_kb_chunks(self, records: list[dict[str, Any]]) -> int:
        """Upsert knowledge-base chunk records."""
        ...

    def search_kb(
        self,
        query_vector: list[float],
        top_k: int = 10,
        collection: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over knowledge-base chunks."""
        ...

    def delete_kb_by_doc(self, doc_id: str) -> int:
        """Remove all vector chunks for a given document."""
        ...

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------
    def get_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        ...

    def compact(self) -> None:
        """Compact / optimize underlying storage."""
        ...
