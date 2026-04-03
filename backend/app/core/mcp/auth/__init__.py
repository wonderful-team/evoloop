"""MCP Authentication module - handles various auth methods."""

from app.core.mcp.auth.base import AuthConfig, AuthHandler, AuthMethod, AuthToken
from app.core.mcp.auth.elicitation import (
    ElicitationField,
    ElicitationRequest,
    mcp_elicitation_handler,
)
from app.core.mcp.auth.manager import mcp_auth_manager
from app.core.mcp.auth.oauth_flows import (
    OAuthAuthorizationCodeHandler,
    OAuthDeviceCodeHandler,
)

__all__ = [
    # Base
    "AuthConfig",
    "AuthHandler",
    "AuthMethod",
    "AuthToken",
    # OAuth
    "OAuthAuthorizationCodeHandler",
    "OAuthDeviceCodeHandler",
    # Manager
    "mcp_auth_manager",
    # Elicitation
    "ElicitationField",
    "ElicitationRequest",
    "mcp_elicitation_handler",
]
