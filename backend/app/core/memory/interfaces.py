"""Memory system interfaces.

Only ``IShortTermMemory`` is actively used (by ``SqlShortTermMemory``
and ``MemoryManager`` type hints).
"""

from abc import ABC, abstractmethod

from app.core.engine.message.native_classes import BaseMessage
from app.core.memory.constants import DEFAULT_SEARCH_LIMIT


class IShortTermMemory(ABC):
    """Interface for short-term (session-based) memory.

    Implemented by ``SqlShortTermMemory`` and used as a type hint
    in ``MemoryManager``.
    """

    @abstractmethod
    async def initialize(self) -> None:
        pass

    @abstractmethod
    async def flush(self) -> None:
        pass

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
    async def search_messages(
        self,
        query: str,
        thread_id: str | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[BaseMessage]:
        pass
