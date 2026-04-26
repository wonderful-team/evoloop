from abc import ABC, abstractmethod

from app.core.evocloud.interfaces.client import EvoCloudClientProtocol
from app.core.evocloud.schemas import EvoCloudConfig


class DeviceLinkProtocol(ABC):
    """Protocol for Real-time Device Link (WebSocket)."""

    @abstractmethod
    def __init__(self, config: EvoCloudConfig, api_client: EvoCloudClientProtocol):
        """Initialize with config and API client (for registration/updates)."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start the connection loop."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the connection."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check connection status."""
        pass

    @property
    @abstractmethod
    def device_key(self) -> str:
        """Get the registered device key."""
        pass
