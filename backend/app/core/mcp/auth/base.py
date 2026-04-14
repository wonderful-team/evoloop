"""Base class for MCP authentication handlers."""

from abc import ABC, abstractmethod
from enum import Enum

from app.infrastructure.pydantic_base import DynamicBaseModel


class AuthMethod(str, Enum):
    """Authentication methods for MCP servers."""
    API_KEY = "api_key"
    OAUTH_AUTH_CODE = "oauth_authorization_code"
    OAUTH_DEVICE_CODE = "oauth_device_code"
    OAUTH_CLIENT_CREDENTIALS = "oauth_client_credentials"


class AuthToken(DynamicBaseModel):
    """Authentication token data."""
    access_token: str
    token_type: str = "Bearer"
    expires_at: float | None = None  # Unix timestamp
    refresh_token: str | None = None
    scope: str | None = None
    
    def is_expired(self, buffer_seconds: int = 60) -> bool:
        """Check if token is expired (with buffer)."""
        import time
        if self.expires_at is None:
            return False
        return time.time() >= (self.expires_at - buffer_seconds)


class AuthConfig(DynamicBaseModel):
    """Authentication configuration for an MCP server."""
    method: AuthMethod
    # API Key auth
    api_key: str | None = None
    api_key_header: str = "X-API-Key"
    # OAuth common
    client_id: str | None = None
    client_secret: str | None = None
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    scopes: list[str] | None = None
    # OAuth Authorization Code
    redirect_uri: str = "http://localhost:8877/oauth/callback"
    # OAuth Device Code
    device_authorization_endpoint: str | None = None


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
