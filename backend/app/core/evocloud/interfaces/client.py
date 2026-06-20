from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

import httpx

from app.core.evocloud.schemas import EvoCloudConfig
from app.models.schemas.auth import LoginResult


class EvoCloudClientProtocol(ABC):
    """Protocol for EvoCloud REST API operations."""

    @abstractmethod
    def __init__(self, config: EvoCloudConfig):
        """Initialize with configuration."""
        pass

    @abstractmethod
    async def get_client(self) -> httpx.AsyncClient:
        """Get the underlying HTTP client."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close connections."""
        pass

    # --- Auth ---
    @abstractmethod
    def set_token(self, token: str | None) -> None:
        """Update the access token used for requests."""
        pass

    @abstractmethod
    def get_token(self) -> str | None:
        """Get current access token."""
        pass

    @abstractmethod
    def on_token_change(self, callback: Callable[[str | None], None]) -> None:
        """Register a callback invoked whenever the access token changes."""
        pass

    @abstractmethod
    async def refresh_access_token(self, failed_token: str | None = None) -> str | None:
        """Refresh the access token using a refresh token."""
        pass

    # --- Core Requests ---
    @abstractmethod
    async def request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Execute a raw request to EvoCloud."""
        pass

    # --- Business Methods (Subset) ---
    # To keep the interface clean, we might not list ALL 50+ methods here if they are just proxies.
    # But for a strict interface, we should. For now, let's define key categories.

    @abstractmethod
    async def login(self, username, password) -> LoginResult: ...

    @abstractmethod
    async def register_device(self, key: str, name: str, os_info: str, token: str | None = None) -> dict: ...

    @abstractmethod
    async def send_heartbeat(self, device_key: str, token: str | None = None): ...

    @abstractmethod
    async def bind_client_id(self, device_key, client_id, token: str | None = None): ...

    @abstractmethod
    async def upload_file(self, file_path: str, token: str | None = None) -> dict: ...
