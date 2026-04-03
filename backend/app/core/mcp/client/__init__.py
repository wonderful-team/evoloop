"""MCP Client module - manages connections to external MCP servers."""

from app.core.mcp.client.manager import McpClientManager, mcp_client_manager
from app.core.mcp.config import (
    AuthType,
    ConnectionResult,
    ConnectionState,
    McpServerConfig,
    TransportType,
)
from app.core.mcp.features import (
    McpPromptsFeature,
    McpResourcesFeature,
    McpToolsFeature,
)
from app.core.mcp.health import HealthStatus, McpHealthChecker
from app.core.mcp.transport import McpTransport, restore_std_streams

__all__ = [
    # Manager
    "McpClientManager",
    "mcp_client_manager",
    # Config
    "McpServerConfig",
    "TransportType",
    "AuthType",
    "ConnectionResult",
    "ConnectionState",
    # Features
    "McpToolsFeature",
    "McpResourcesFeature",
    "McpPromptsFeature",
    # Health
    "McpHealthChecker",
    "HealthStatus",
    # Transport
    "McpTransport",
    "restore_std_streams",
]
