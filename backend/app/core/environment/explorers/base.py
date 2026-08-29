import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseExplorer(ABC):
    """
    Abstract Base Class for platform-specific environment explorers.
    """

    @abstractmethod
    async def scan(self, *args, **kwargs) -> list:
        """Perform a basic environment scan (e.g. list apps)."""
        pass
