"""Shared constants for the MCP subsystem.

This module holds numeric tuning values and string literals that are used
across the MCP client, features, and configuration. Enums such as
:class:`app.core.mcp.config.TransportType` and
:class:`app.core.mcp.config.AuthType` remain in their dedicated enum modules.
"""

# ====================== Client timeouts ======================
#: Seconds to wait for an MCP session ``initialize()`` to complete.
MCP_CONNECT_TIMEOUT = 20.0
#: Seconds between keepalive pings for an active MCP session.
MCP_KEEPALIVE_INTERVAL = 10.0
#: Seconds to wait for a single keepalive ping response.
MCP_PING_TIMEOUT = 5.0

# ====================== Tool name formatting ======================
#: Prefix used when flattening MCP tool names into the native tool namespace.
MCP_TOOL_NAME_PREFIX = "mcp__"
#: Separator between server name and original tool name.
MCP_TOOL_NAME_SEPARATOR = "__"
