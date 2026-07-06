"""Base class for MCP authentication handlers."""

from abc import ABC, abstractmethod
from enum import Enum

from app.core.mcp.schemas.auth import AuthConfig, AuthToken


class AuthMethod(str, Enum):
    """Authentication methods for MCP servers."""
    API_KEY = "api_key"
    OAUTH_AUTH_CODE = "oauth_authorization_code"
    OAUTH_DEVICE_CODE = "oauth_device_code"
    OAUTH_CLIENT_CREDENTIALS = "oauth_client_credentials"


class AuthHandler(ABC):
    """Base class for MCP authentication handlers."""

    def __init__(self, server_name: str, config: AuthConfig):
        self.server_name = server_name
        self.config = config

    @property
    @abstractmethod
    def method(self) -> AuthMethod:
        """Return the auth method this handler supports."""
        pass

    @abstractmethod
    async def authenticate(self) -> AuthToken:
        """Perform authentication and return token."""
        pass

    @abstractmethod
    async def refresh(self, token: AuthToken) -> AuthToken:
        """Refresh an existing token."""
        pass

    def get_headers(self, token: AuthToken) -> dict[str, str]:
        """Get HTTP headers for authentication."""
        return {"Authorization": f"{token.token_type} {token.access_token}"}
