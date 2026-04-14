from abc import ABC, abstractmethod
from collections.abc import Callable

from app.core.evocloud.interfaces.client import EvoCloudClientProtocol
from app.core.evocloud.schemas import EvoCloudConfig, ProjectSwitchEvent, RemoteCommand


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
    def device_id(self) -> int | None:
        """Get the registered device ID."""
        pass

    # --- Callbacks ---
    @abstractmethod
    def set_command_handler(self, handler: Callable[[RemoteCommand], None]) -> None:
        """Set handler for incoming remote commands."""
        pass

    @abstractmethod
    def set_event_handler(self, handler: Callable[[str, ProjectSwitchEvent], None]) -> None:
        """Set handler for other events (e.g. project_switch)."""
        pass
