"""
Client-side Tool Execution Router

Routes tool execution to Client when appropriate:
- Local-only tools (file, shell, MCP) → Client via WebSocket/HTTP
- Cloud-native tools → Execute directly in Backend

This module provides decorators and wrappers for transparent routing.
"""

import logging
from functools import wraps
from typing import Any, Callable

from app.core.config import settings
from app.infrastructure.client import get_client_executor, ToolExecutionError

logger = logging.getLogger(__name__)

# Tools that should be executed via Client (local-only tools)
# These tools require local environment access (filesystem, shell, devices, browser, desktop)
CLIENT_TOOLS = {
    # File operations
    "file_read",
    "file_write",
    "file_list",
    "file_edit",
    "file_delete",
    "file_search",
    "file_search_name",
    "file_open",
    # Shell execution
    "shell",
    "shell_execute",
    # Python execution (local only)
    "python_execute",
    "exec_python",
    # ADB (Android Debug Bridge) - device automation
    "adb_connect",
    "adb_shell",
    "adb_screenshot",
    "adb_tap",
    "adb_swipe",
    "adb_dump_ui",
    "adb_input",
    "adb_key",
    "adb_get_current_app",
    # Browser automation
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_screenshot",
    "browser_get_html",
    "browser_get_url",
    "browser_back",
    "browser_forward",
    "browser_refresh",
    "browser_close",
    # Desktop automation
    "desktop_screenshot",
    "desktop_click",
    "desktop_type",
    "desktop_key",
    "desktop_get_cursor",
    # MCP tool execution
    "mcp",
    # Context retrieval
    "get_context",
}


def should_use_client(tool_name: str) -> bool:
    """
    Check if a tool should be executed via Client.

    First checks if connected Client reports supporting this tool via
    capabilities message (WebSocket or HTTP). Falls back to hardcoded list
    if no capabilities reported yet (backward compatibility).
    """
    if not settings.USE_CLIENT_FOR_TOOLS:
        return False

    # Priority 1: Check WebSocket capabilities
    from app.infrastructure.client import client_ws_manager

    if client_ws_manager.is_connected():
        # If client reported capabilities, use them
        if client_ws_manager.get_supported_tools():
            return client_ws_manager.supports_tool(tool_name)
        # Client connected but no capabilities yet - assume support during transition
        return True

    # Priority 2: Check HTTP mode capabilities
    from app.infrastructure.client.http import client_capabilities

    if client_capabilities.is_reported():
        return client_capabilities.supports_tool(tool_name)

    # Priority 3: Fallback to hardcoded list (backward compatibility)
    # This handles HTTP mode before capabilities are reported
    if tool_name in CLIENT_TOOLS:
        return True

    # Check for MCP tools (mcp__server__tool format)
    if tool_name.startswith("mcp__"):
        return True

    # Check for device/browser/desktop automation tools (prefix matching)
    local_prefixes = ("adb_", "browser_", "desktop_")
    if tool_name.startswith(local_prefixes):
        return True

    return False


async def execute_via_client(
    thread_id: str,
    tool_name: str,
    params: dict[str, Any]
) -> Any:
    """
    Execute a tool via Client.

    Args:
        thread_id: The conversation thread ID
        tool_name: Name of the tool to execute
        params: Tool parameters

    Returns:
        Tool execution result
    """
    executor = get_client_executor()

    try:
        result = await executor.execute(
            thread_id=thread_id,
            tool=tool_name,
            params=params,
            timeout=getattr(settings, 'CLIENT_TOOL_TIMEOUT', 300.0)
        )
        return result
    except ToolExecutionError as e:
        logger.error(f"[ClientExecutor] Tool execution failed: {e}")
        raise
    except Exception as e:
        logger.error(f"[ClientExecutor] Unexpected error: {e}")
        raise ToolExecutionError(f"Failed to execute {tool_name}: {e}")


def wrap_tool_for_client(tool_func: Callable) -> Callable:
    """
    Decorator to wrap a tool function for Client execution.

    Usage:
        @wrap_tool_for_client
        async def file_read(path: str) -> str:
            ...
    """
    @wraps(tool_func)
    async def wrapper(*args, **kwargs):
        # Get thread_id from context if available
        from app.core.context.manager import ContextManager

        ctx = ContextManager.current()
        thread_id = ctx.thread_id if ctx else "unknown"

        tool_name = tool_func.__name__

        # Check if we should use Client
        if should_use_client(tool_name):
            logger.info(f"[ClientExecutor] Routing {tool_name} via Client for thread {thread_id}")

            # Convert args/kwargs to params dict
            params = kwargs.copy()
            if args:
                # Try to map positional args to first param names
                import inspect
                sig = inspect.signature(tool_func)
                param_names = list(sig.parameters.keys())
                for i, arg in enumerate(args):
                    if i < len(param_names):
                        params[param_names[i]] = arg

            return await execute_via_client(thread_id, tool_name, params)
        else:
            # Execute locally
            return await tool_func(*args, **kwargs)

    return wrapper


class ClientToolWrapper:
    """
    Wrapper for LangChain tools to route execution through Client.
    """

    def __init__(self, tool: Any):
        self._tool = tool
        self.name = tool.name
        self.description = tool.description
        self.args_schema = getattr(tool, "args_schema", None)

    async def ainvoke(self, input: Any, config: Any = None) -> Any:
        """Execute tool, routing through Client if configured."""
        from app.core.context.manager import ContextManager

        ctx = ContextManager.current()
        thread_id = ctx.thread_id if ctx else "unknown"

        if should_use_client(self.name):
            # Convert input to params dict
            if isinstance(input, dict):
                params = input
            else:
                params = {"input": input}

            logger.info(f"[ClientToolWrapper] Routing {self.name} via Client")
            return await execute_via_client(thread_id, self.name, params)
        else:
            # Execute locally using original tool
            return await self._tool.ainvoke(input, config)

    def __getattr__(self, name: str):
        """Delegate attribute access to wrapped tool."""
        return getattr(self._tool, name)


def wrap_tools_for_client(tools: list[Any]) -> list[Any]:
    """
    Wrap a list of tools for Client execution.

    Args:
        tools: List of LangChain tools

    Returns:
        List of wrapped tools
    """
    if not settings.USE_CLIENT_FOR_TOOLS:
        return tools

    wrapped = []
    for tool in tools:
        if should_use_client(tool.name):
            wrapped.append(ClientToolWrapper(tool))
        else:
            wrapped.append(tool)

    return wrapped
