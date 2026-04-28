"""
Long-term Memory Interfaces.
Defines models and interfaces for domain-specific knowledge (Concepts) 
and execution history (Episodes).
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from app.core.memory.models import Concept, Episode
from app.core.memory.schemas import SearchResult


class ILongTermMemory(ABC):
    """Interface for long-term knowledge storage (e.g., Neo4j)."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize backend storage/indexes."""
        pass

    @abstractmethod
    async def flush(self) -> None:
        """Clear all data (for testing)."""
        pass

    @abstractmethod
    async def store_concept(self, concept: Concept) -> None:
        """Store a domain concept."""
        pass

    @abstractmethod
    async def search_concepts(
        self, query: str, project_id: Optional[int] = None, min_score: float = 0.7
    ) -> List[SearchResult]:
        """Semantic search for concepts."""
        pass

    @abstractmethod
    async def search_concepts_data(self, query: str, project_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Raw data version of search."""
        pass

    @abstractmethod
    async def record_episode(self, episode: Episode) -> Optional[str]:
        """Record an execution attempt."""
        pass

    @abstractmethod
    async def retrieve_experience(self, goal: str, project_id: int, top_k: int = 3) -> str:
        """Find past episodes similar to goal."""
        pass

    @abstractmethod
    async def get_project_concepts(self, project_id: int) -> List[str]:
        """Get all concepts for a project."""
        pass

    @abstractmethod
    async def find_episodes_by_concept(self, concept_name: str, project_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Find episodes linked to a concept."""
        pass
