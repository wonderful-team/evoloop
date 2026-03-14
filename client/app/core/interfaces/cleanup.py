from abc import ABC, abstractmethod


class ICleanupHandler(ABC):
    """
    Interface for components that need to perform cleanup 
    when a conversation turn is rolled back.
    """

    @abstractmethod
    async def cleanup(self, message_ids: list[str]) -> int:
        """
        Clean up artifacts linked to the given message IDs.
        
        Args:
            message_ids: List of source message IDs that are being deleted.
            
        Returns:
            Number of items deleted/cleaned up.
        """
        pass
