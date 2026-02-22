from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.evocloud.schemas import EvoCloudConfig


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

    # --- Core Requests ---
    @abstractmethod
    async def request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Execute a raw request to EvoCloud."""
        pass

    # --- Business Methods (Subset) ---
    # To keep the interface clean, we might not list ALL 50+ methods here if they are just proxies.
    # But for a strict interface, we should. For now, let's define key categories.

    @abstractmethod
    async def login(self, username, password) -> dict: ...

    @abstractmethod
    async def register_device(self, key: str, name: str, os_info: str) -> dict: ...

    @abstractmethod
    async def upload_log(self, device_id: int, thread_id: str, log_type: str, content: Any, command_id=None, project_id=None, persistent: bool = True): ...

