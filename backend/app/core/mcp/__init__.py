"""
EvoLoop MCP (Model Context Protocol) Core Module.

This module provides standardized MCP client functionality for connecting to
external MCP servers and using their tools, resources, and prompts.

Architecture:
    ┌─────────────────────────────────────────┐
    │         app/core/mcp/                   │
    │  ┌─────────────────────────────────────┐│
    │  │  client/   - Connection management  ││
    │  │  • manager.py - Main entry point    ││
    │  │  • transport.py - Stdio/SSE         ││
    │  │  • health.py - Health checking      ││
    │  └─────────────────────────────────────┘│
    │  ┌─────────────────────────────────────┐│
    │  │  features/ - MCP protocol features  ││
    │  │  • tools.py - Tools support         ││
    │  │  • resources.py - Resources support ││
    │  │  • prompts.py - Prompts support     ││
    │  └─────────────────────────────────────┘│
    │  ┌─────────────────────────────────────┐│
    │  │  auth/ - Authentication             ││
    │  │  • oauth_flows.py - OAuth 2.0       ││
    │  │  • elicitation.py - URL Elicitation ││
    │  │  • manager.py - Auth management     ││
    │  └─────────────────────────────────────┘│
    │  ┌─────────────────────────────────────┐│
    │  │  config.py - Configuration models   ││
    │  └─────────────────────────────────────┘│
    └─────────────────────────────────────────┘

Usage:
    from app.core.mcp import mcp_client_manager
    
    # Connect to all enabled servers
    results = await mcp_client_manager.connect_all()
    
    # Get tools from a specific server
    tools = await mcp_client_manager.get_tools("github")
    
    # Ensure connection before use
    if await mcp_client_manager.ensure_connected("postgres"):
        tools = await mcp_client_manager.get_tools("postgres")
    
    # Access resources
    resources = await mcp_client_manager.list_resources("github")
    content = await mcp_client_manager.read_resource("github", "file://readme.md")
    
    # Access prompts
    prompts = await mcp_client_manager.list_prompts("github")
    prompt = await mcp_client_manager.get_prompt("github", "review_pr", {"pr_number": "123"})
    
    # OAuth authentication is automatic based on server config
"""

from app.core.mcp.auth import (
    AuthConfig,
    AuthMethod,
    AuthToken,
    ElicitationRequest,
    mcp_auth_manager,
    mcp_elicitation_handler,
)
from app.core.mcp.client import (
    ConnectionResult,
    ConnectionState,
    McpClientManager,
    McpHealthChecker,
    McpPromptsFeature,
    McpResourcesFeature,
    McpServerConfig,
    McpToolsFeature,
    McpTransport,
    TransportType,
    mcp_client_manager,
    restore_std_streams,
)
from app.core.mcp.config import AuthType
from app.core.mcp.worker import WorkerMcpSession, worker_mcp_manager
from app.core.mcp.worker_config import WorkerMcpConfig, WorkerMcpServerConfig

__all__ = [
    # Main entry point
    "mcp_client_manager",
    "McpClientManager",
    # Configuration
    "McpServerConfig",
    "TransportType",
    "AuthType",
    "ConnectionResult",
    "ConnectionState",
    # Features
    "McpToolsFeature",
    "McpResourcesFeature",
    "McpPromptsFeature",
    # Auth
    "AuthConfig",
    "AuthMethod",
    "AuthToken",
    "mcp_auth_manager",
    "mcp_elicitation_handler",
    "ElicitationRequest",
    # Worker MCP
    "WorkerMcpSession",
    "worker_mcp_manager",
    "WorkerMcpConfig",
    "WorkerMcpServerConfig",
    # Infrastructure
    "McpHealthChecker",
    "McpTransport",
    "restore_std_streams",
]
