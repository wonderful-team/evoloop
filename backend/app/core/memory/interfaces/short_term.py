"""Short-term memory interface for managing conversation context."""

from abc import abstractmethod

from langchain_core.messages import BaseMessage

from app.core.memory.interfaces.base import IMemoryProvider


class IShortTermMemory(IMemoryProvider):
    """
    Interface for short-term (session-based) memory.
    Handles volatile conversation context and message history.
    """

    @abstractmethod
    async def add_message(self, thread_id: str, message: BaseMessage) -> None:
        """
        Add a message to the conversation history.

        Args:
            thread_id: The conversation thread identifier
            message: The message to store
        """
        pass

    @abstractmethod
    async def get_context(self, thread_id: str, limit: int = 50) -> list[BaseMessage]:
        """
        Retrieve recent conversation context.

        Args:
            thread_id: The conversation thread identifier
            limit: Maximum number of messages to retrieve

        Returns:
            List of messages in chronological order
        """
        pass

    @abstractmethod
    async def prune(self, thread_id: str) -> None:
        """
        Apply pruning strategy to reduce token pressure.

        Args:
            thread_id: The conversation thread to prune
        """
        pass

    @abstractmethod
    async def search_messages(self, query: str, thread_id: str | None = None, limit: int = 10) -> list[BaseMessage]:
        """
        Search for messages containing the query string.

        Args:
            query: The search term
            thread_id: Optional thread ID to narrow search
            limit: Maximum results

        Returns:
            List of matching messages
        """
        pass
