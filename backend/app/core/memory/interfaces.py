"""Memory system interfaces and storage exceptions.

Only ``IShortTermMemory`` is actively used (by ``SqlShortTermMemory``
and ``MemoryManager`` type hints). The other interfaces are kept as
documentation for future backend implementations.
"""

from abc import ABC, abstractmethod
from typing import Any

from app.core.engine.message.native_classes import BaseMessage
from app.core.memory.schemas import Concept, Episode, SearchResult


class StorageError(Exception):
    """Base exception for storage operations.

    Currently unused — defined for future backend implementations.
    """

    pass


class StorageNotFoundError(StorageError):
    """Raised when a memory entry is not found.

    Currently unused — defined for future backend implementations.
    """

    pass


class StorageConnectionError(StorageError):
    """Raised when connection to storage backend fails.

    Currently unused — defined for future backend implementations.
    """

    pass


class IMemoryProvider(ABC):
    """Base interface for memory system components.

    Currently only ``IShortTermMemory`` extends this.
    """

    @abstractmethod
    async def initialize(self) -> None:
        pass

    @abstractmethod
    async def flush(self) -> None:
        pass


class IShortTermMemory(IMemoryProvider):
    """Interface for short-term (session-based) memory.

    Implemented by ``SqlShortTermMemory`` and used as a type hint
    in ``MemoryManager``.
    """

    @abstractmethod
    async def add_message(self, thread_id: str, message: BaseMessage) -> None:
        pass

    @abstractmethod
    async def get_context(self, thread_id: str, limit: int = 50) -> list[BaseMessage]:
        pass

    @abstractmethod
    async def prune(self, thread_id: str) -> None:
        pass

    @abstractmethod
    async def search_messages(self, query: str, thread_id: str | None = None, limit: int = 10) -> list[BaseMessage]:
        pass


class ILongTermMemory(ABC):
    """Interface for long-term knowledge storage.

    Not currently implemented by any class. The methods mirror what
    ``MemoryManager`` delegates to ``_FileEngine`` / ``_GraphEngine``
    via ``MemoryStore``. If a future backend needs formal enforcement,
    have ``MemoryStore`` or ``_FileEngine`` declare ``class MemoryStore(ILongTermMemory)``.
    """

    @abstractmethod
    async def initialize(self) -> None:
        pass

    @abstractmethod
    async def flush(self) -> None:
        pass

    @abstractmethod
    async def store_concept(self, concept: Concept) -> None:
        pass

    @abstractmethod
    async def search_concepts(
        self, query: str, project_id: int | None = None, min_score: float = 0.7
    ) -> list[SearchResult]:
        pass

    @abstractmethod
    async def search_concepts_data(self, query: str, project_id: int | None = None) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    async def record_episode(self, episode: Episode) -> str | None:
        pass

    @abstractmethod
    async def retrieve_experience(self, goal: str, project_id: int, top_k: int = 3) -> str:
        pass

    @abstractmethod
    async def get_project_concepts(self, project_id: int) -> list[str]:
        pass

    @abstractmethod
    async def find_episodes_by_concept(self, concept_name: str, project_id: int, limit: int = 10) -> list[dict[str, Any]]:
        pass
