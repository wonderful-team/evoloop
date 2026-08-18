"""OAuth manager for MCP servers."""

import logging
from typing import Any

from app.core.mcp.auth.base import AuthConfig, AuthHandler, AuthMethod, AuthToken
from app.core.mcp.auth.oauth_flows import (
    OAuthAuthorizationCodeHandler,
    OAuthDeviceCodeHandler,
)

logger = logging.getLogger(__name__)


class McpAuthManager:
    """
    Manages authentication for MCP servers.

    Handles multiple auth methods:
    - API Key (via headers/env)
    - OAuth 2.0 Authorization Code
    - OAuth 2.0 Device Code
    """

    def __init__(self):
        self._handlers: dict[str, AuthHandler] = {}
        self._tokens: dict[str, AuthToken] = {}

    def create_handler(self, server_name: str, auth_config: dict[str, Any]) -> AuthHandler | None:
        """
        Create appropriate auth handler based on config.

        Args:
            server_name: MCP server name
            auth_config: Auth configuration dict

        Returns:
            AuthHandler instance or None if no auth needed
        """
        method = auth_config.get("method", "api_key")

        if method == AuthMethod.API_KEY:
            # API Key is handled via headers/env, no handler needed
            return None

        elif method == AuthMethod.OAUTH_AUTH_CODE:
            config = AuthConfig(
                method=AuthMethod.OAUTH_AUTH_CODE,
                client_id=auth_config.get("client_id"),
                client_secret=auth_config.get("client_secret"),
                authorization_endpoint=auth_config.get("authorization_endpoint"),
                token_endpoint=auth_config.get("token_endpoint"),
                redirect_uri=auth_config.get("redirect_uri", "http://localhost:8877/oauth/callback"),
                scopes=auth_config.get("scopes", []),
            )
            handler = OAuthAuthorizationCodeHandler(server_name, config)
            self._handlers[server_name] = handler
            return handler

        elif method == AuthMethod.OAUTH_DEVICE_CODE:
            config = AuthConfig(
                method=AuthMethod.OAUTH_DEVICE_CODE,
                client_id=auth_config.get("client_id"),
                client_secret=auth_config.get("client_secret"),
                device_authorization_endpoint=auth_config.get("device_authorization_endpoint"),
                token_endpoint=auth_config.get("token_endpoint"),
                scopes=auth_config.get("scopes", []),
            )
            handler = OAuthDeviceCodeHandler(server_name, config)
            self._handlers[server_name] = handler
            return handler

        else:
            logger.warning(f"Unknown auth method: {method}")
            return None

    async def authenticate(self, server_name: str) -> AuthToken | None:
        """
        Authenticate with a server.

        Args:
            server_name: Server to authenticate with

        Returns:
            AuthToken or None
        """
        handler = self._handlers.get(server_name)
        if not handler:
            return None

        try:
            token = await handler.authenticate()
            self._tokens[server_name] = token
            return token
        except Exception as e:
            logger.exception(f"Authentication failed for {server_name}: {e}")
            raise

    async def get_token(self, server_name: str) -> AuthToken | None:
        """
        Get valid token for a server, refreshing if needed.

        Args:
            server_name: Server name

        Returns:
            Valid AuthToken or None
        """
        token = self._tokens.get(server_name)

        if not token:
            return None

        # Check if expired and refresh
        if token.is_expired():
            handler = self._handlers.get(server_name)
            if handler:
                logger.info(f"Refreshing token for {server_name}")
                token = await handler.refresh(token)
                self._tokens[server_name] = token

        return token

    def get_headers(self, server_name: str) -> dict[str, str]:
        """
        Get authentication headers for a server.

        Args:
            server_name: Server name

        Returns:
            Headers dict (empty if no auth)
        """
        token = self._tokens.get(server_name)
        if token:
            handler = self._handlers.get(server_name)
            if handler:
                return handler.get_headers(token)
        return {}

    def remove_handler(self, server_name: str) -> None:
        """Remove handler for a server."""
        self._handlers.pop(server_name, None)
        self._tokens.pop(server_name, None)

    async def handle_oauth_callback(self, server_name: str, url: str) -> None:
        """
        Handle OAuth callback for a server.

        Args:
            server_name: Server name
            url: Callback URL
        """
        handler = self._handlers.get(server_name)
        if handler and isinstance(handler, OAuthAuthorizationCodeHandler):
            await handler.handle_callback(url)
        else:
            raise ValueError(f"No OAuth handler for {server_name}")


# Global instance
mcp_auth_manager = McpAuthManager()
