"""
Memory Storage Abstract Interface

Defines the contract for all memory storage backends.
This ensures FileMemoryStorage, Neo4jMemoryStorage, and future backends
are interchangeable.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from app.core.memory.models import (
    MemoryEntry,
    MemorySearchResult,
    MemoryType,
    PrivacyLevel,
)
from app.core.memory.schemas import StorageHealthCheck


class IMemoryStorage(ABC):
    """
    Abstract interface for memory storage backends.
    
    All storage implementations (File, Neo4j, etc.) must implement this interface
to ensure they are interchangeable and can be used polymorphically.
    
    Usage:
        storage: IMemoryStorage = MemoryStorageFactory.create_storage(config)
        await storage.save(entry)
        results = await storage.search("query", project_id=42)
    """

    # ==========================================================================
    # Basic CRUD Operations (Required)
    # ==========================================================================

    @abstractmethod
    async def save(self, entry: "MemoryEntry") -> None:
        """
        Save a memory entry to storage.
        
        Args:
            entry: Memory entry to save
            
        Raises:
            StorageError: If save operation fails
        """
        pass

    @abstractmethod
    async def get(self, entry_id: str) -> Optional["MemoryEntry"]:
        """
        Retrieve a memory entry by ID.
        
        Args:
            entry_id: Unique identifier of the memory entry
            
        Returns:
            Memory entry if found, None otherwise
        """
        pass

    @abstractmethod
    async def find_by_hash(self, content_hash: str, project_id: Optional[int] = None) -> Optional["MemoryEntry"]:
        """
        Find a memory entry by its content hash.
        Used for global de-duplication across sessions.
        
        Args:
            content_hash: SHA-256 fingerprint of the content
            project_id: Optional project scope
            
        Returns:
            Matching memory entry if found, None otherwise
        """
        pass

    async def get_multi(self, entry_ids: list[str]) -> dict[str, "MemoryEntry"]:
        """
        Retrieve multiple memory entries by IDs (batch operation).

        Default implementation iterates over get(). Backends should override
        for more efficient batch loading.

        Args:
            entry_ids: List of memory entry IDs

        Returns:
            Dictionary mapping entry_id -> MemoryEntry for found entries
        """
        results = {}
        for entry_id in entry_ids:
            entry = await self.get(entry_id)
            if entry:
                results[entry_id] = entry
        return results

    @abstractmethod
    async def delete(self, entry_id: str) -> bool:
        """
        Delete a memory entry.
        
        Args:
            entry_id: ID of the entry to delete
            
        Returns:
            True if deleted successfully, False if not found
        """
        pass

    # ==========================================================================
    # Query Operations (Required)
    # ==========================================================================

    @abstractmethod
    async def search(
        self,
        query: str,
        types: list["MemoryType"] | None = None,
        privacy: Optional["PrivacyLevel"] = None,
        project_id: int | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list["MemoryEntry"]:
        """
        Search memory entries by text query.
        
        Implementation can vary by backend:
        - File: Keyword matching
        - Neo4j: Vector similarity + keyword
        
        Args:
            query: Search query text
            types: Filter by memory types
            privacy: Filter by privacy level
            project_id: Filter by project ID
            limit: Maximum number of results
            
        Returns:
            List of matching memory entries
        """
        pass

    @abstractmethod
    async def list_all(
        self,
        type_filter: Optional["MemoryType"] = None,
        privacy_filter: Optional["PrivacyLevel"] = None,
        project_id: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list["MemorySearchResult"]:
        """
        List memory entries (lightweight, for indexing and UI listing).
        
        Args:
            type_filter: Filter by type
            privacy_filter: Filter by privacy
            project_id: Optional project filter
            limit: Optional maximum number of results
            
        Returns:
            List of memory search results
        """
        pass

    # ==========================================================================
    # Advanced Operations (Optional - may raise NotImplementedError)
    # ==========================================================================

    async def search_similar(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        project_id: int | None = None,
    ) -> list["MemoryEntry"]:
        """
        Search by vector similarity (semantic search).
        
        Optional operation. Backends without vector support should
        raise NotImplementedError.
        
        Args:
            query_embedding: Vector embedding of the query
            top_k: Number of top results to return
            project_id: Filter by project
            
        Returns:
            List of similar memory entries
            
        Raises:
            NotImplementedError: If backend doesn't support vector search
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support vector search")

    async def get_related(
        self,
        entry_id: str,
        relation_type: str | None = None,
        limit: int = 10,
    ) -> list["MemoryEntry"]:
        """
        Get memories related to a given entry (graph traversal).
        
        Optional operation for graph-based backends.
        
        Args:
            entry_id: Source memory ID
            relation_type: Type of relationship (e.g., "related_to", "child_of")
            limit: Maximum number of related memories
            
        Returns:
            List of related memory entries
            
        Note:
            Non-graph backends may return empty list
        """
        return []

    @abstractmethod
    async def get_recent(self, count: int = 5, project_id: int | None = None) -> list["MemoryEntry"]:
        """
        Get most recently updated memory entries.
        
        Args:
            count: Number of entries to return
            
        Returns:
            List of memory entries
        """
        pass

    async def get_by_project(
        self,
        project_id: int,
        limit: int = 100,
    ) -> list["MemoryEntry"]:
        """
        Get all memories for a specific project.
        
        Default implementation uses list_all then filters.
        Backends should override for more efficiency.
        """
        all_memories = await self.list_all(project_id=project_id, limit=limit)
        results = []
        for mem in all_memories:
            entry = await self.get(mem.id)
            if entry:
                results.append(entry)
        return results

    # ==========================================================================
    # Relationship Operations (Optional)
    # ==========================================================================

    async def link_concept_to_episode(self, concept_name: str, episode_id: str) -> None:
        """
        Create a link between a concept and an episode.
        """
        pass

    async def find_episodes_by_concept(self, concept_name: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Find all episodes linked to a specific concept.
        """
        return []

    async def get_all_concept_counts(self) -> dict[str, int]:
        """
        Efficiently retrieve counts of linked episodes for all concepts.
        
        Returns:
            Dict mapping concept_name -> episode_count
        """
        return {}

    # ==========================================================================
    # Lifecycle Methods
    # ==========================================================================

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the storage backend.
        
        May include:
        - Creating directories (File)
        - Establishing connections (Neo4j)
        - Creating indexes
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Close the storage backend and release resources.
        
        Should be called during shutdown.
        """
        pass

    async def flush(self) -> None:
        """
        Clear all data (for testing).
        
        Optional operation. Default does nothing.
        """
        pass

    # ==========================================================================
    # Health & Stats
    # ==========================================================================

    async def health_check(self) -> StorageHealthCheck:
        """
        Check storage health status.
        
        Returns:
            Dictionary with health info:
            - status: "healthy" | "degraded" | "unhealthy"
            - latency_ms: Average operation latency
            - entry_count: Total entries (if available)
        """
        return StorageHealthCheck(status="unknown", backend=self.__class__.__name__)


class StorageError(Exception):
    """Base exception for storage operations."""
    pass


class StorageNotFoundError(StorageError):
    """Raised when a memory entry is not found."""
    pass


class StorageConnectionError(StorageError):
    """Raised when connection to storage backend fails."""
    pass
