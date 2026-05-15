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
    # Memory embeddings
    # ------------------------------------------------------------------
    def upsert_memory_chunks(self, records: list[dict[str, Any]]) -> int:
        """Upsert memory chunk records."""
        ...

    def search_memory(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over memory chunks."""
        ...

    def delete_memory_by_id(self, memory_id: str) -> bool:
        """Remove a specific memory entry by its ID."""
        ...

    def delete_all_memories(self) -> int:
        """Wipe all memory entries from the store."""
        ...

    # ------------------------------------------------------------------
    # Learned Skill embeddings
    # ------------------------------------------------------------------
    def upsert_skill_chunks(self, records: list[dict[str, Any]]) -> int:
        """Upsert skill chunk records."""
        ...

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
    def upsert_concept_chunks(self, records: list[dict[str, Any]]) -> int:
        """Upsert graph concept records."""
        ...

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
