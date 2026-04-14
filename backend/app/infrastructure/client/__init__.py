"""
Client Infrastructure Module

Provides communication infrastructure for Backend to connect with Client:
- WebSocket: Low-latency bidirectional communication
- HTTP: Fallback polling mechanism
- Proxy: Unified interface with automatic transport selection
- Executor: Tool execution routing
"""

from .executor import (
    should_use_client,
    execute_via_client,
    wrap_tool_for_client,
    ClientToolWrapper,
    wrap_tools_for_client,
)
from .http import (
    ToolRequest,
    ToolRequestManager,
    ClientToolExecutor,
    ToolExecutionError,
    tool_request_manager,
    get_client_executor,
)
from .proxy import ClientProxy, get_executor, is_proxy_required, client_proxy
from .websocket import (
    ClientWebSocketManager,
    DirectClientToolExecutor,
    client_ws_manager,
    get_direct_client_executor,
)

__all__ = [
    # Proxy (unified interface)
    "ClientProxy",
    "client_proxy",
    "get_executor",
    "is_proxy_required",
    # WebSocket
    "ClientWebSocketManager",
    "DirectClientToolExecutor",
    "client_ws_manager",
    "get_direct_client_executor",
    # HTTP
    "ToolRequest",
    "ToolRequestManager",
    "ClientToolExecutor",
    "ToolExecutionError",
    "tool_request_manager",
    "get_client_executor",
    # Executor (routing)
    "should_use_client",
    "execute_via_client",
    "wrap_tool_for_client",
    "ClientToolWrapper",
    "wrap_tools_for_client",
]
