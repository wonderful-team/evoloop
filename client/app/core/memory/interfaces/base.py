"""Base interface for all memory providers."""

from abc import ABC, abstractmethod


class IMemoryProvider(ABC):
    """
    Base interface for memory system components.
    Defines lifecycle methods common to all memory providers.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the memory provider.
        This may include creating database schemas, indexes, or establishing connections.
        """
        pass

    @abstractmethod
    async def flush(self) -> None:
        """
        Clear or reset the memory provider.
        Useful for testing or session resets.
        """
        pass
