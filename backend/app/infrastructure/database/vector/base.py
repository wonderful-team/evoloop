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

    def delete_by_repository(self, repository_id: str) -> int:
        """Delete all chunks for a repository."""
        ...

    # ------------------------------------------------------------------
    # Memory embeddings
    # ------------------------------------------------------------------
    def search_memory(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over memory chunks."""
        ...

    # ------------------------------------------------------------------
    # Learned Skill embeddings
    # ------------------------------------------------------------------
    def search_skills(
        self,
        query_vector: list[float],
        bundle_id: str | None = None,
        platform: str | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Semantic search over learned skills with optional Atlas filtering."""
        ...

    # ------------------------------------------------------------------
    # Graph Concept embeddings
    # ------------------------------------------------------------------
    def search_concepts(
        self,
        query_vector: list[float],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Semantic search over graph concepts."""
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

    def truncate_all(self) -> None:
        """Wipe all data from all vector tables/collections."""
        ...
