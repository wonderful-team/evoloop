"""
Sidecar-aware Tool Executor

Wraps tool execution to route local tools through Sidecar (Tauri -> Client)
when USE_SIDECAR_FOR_TOOLS is enabled.
"""

import logging
from typing import Any, Callable
from functools import wraps

from app.core.config import settings
from app.core.tools.sidecar_proxy import get_sidecar_executor, ToolExecutionError

logger = logging.getLogger(__name__)

# Tools that should be executed via Sidecar (local-only tools)
SIDECAR_TOOLS = {
    "file_read",
    "file_write",
    "file_list",
    "file_edit",
    "file_delete",
    "shell",
    "shell_execute",
    "python_execute",
    "exec_python",
    "mcp",  # MCP tools may need local execution
}


def should_use_sidecar(tool_name: str) -> bool:
    """Check if a tool should be executed via Sidecar."""
    if not settings.USE_SIDECAR_FOR_TOOLS:
        return False

    # Check exact match or prefix match
    if tool_name in SIDECAR_TOOLS:
        return True

    # Check for MCP tools (mcp__server__tool format)
    if tool_name.startswith("mcp__"):
        return True

    return False


async def execute_via_sidecar(
    thread_id: str,
    tool_name: str,
    params: dict[str, Any]
) -> Any:
    """
    Execute a tool via Sidecar (Tauri -> Client).

    Args:
        thread_id: The conversation thread ID
        tool_name: Name of the tool to execute
        params: Tool parameters

    Returns:
        Tool execution result
    """
    executor = get_sidecar_executor()

    try:
        result = await executor.execute(
            thread_id=thread_id,
            tool=tool_name,
            params=params,
            timeout=settings.SIDECAR_TOOL_TIMEOUT
        )
        return result
    except ToolExecutionError as e:
        logger.error(f"[SidecarExecutor] Tool execution failed: {e}")
        raise
    except Exception as e:
        logger.error(f"[SidecarExecutor] Unexpected error: {e}")
        raise ToolExecutionError(f"Failed to execute {tool_name}: {e}")


def wrap_tool_for_sidecar(tool_func: Callable) -> Callable:
    """
    Decorator to wrap a tool function for Sidecar execution.

    Usage:
        @wrap_tool_for_sidecar
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

        # Check if we should use Sidecar
        if should_use_sidecar(tool_name):
            logger.info(f"[SidecarExecutor] Routing {tool_name} via Sidecar for thread {thread_id}")

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

            return await execute_via_sidecar(thread_id, tool_name, params)
        else:
            # Execute locally
            return await tool_func(*args, **kwargs)

    return wrapper


class SidecarToolWrapper:
    """
    Wrapper for LangChain tools to route execution through Sidecar.
    """

    def __init__(self, tool: Any):
        self._tool = tool
        self.name = tool.name
        self.description = tool.description
        self.args_schema = getattr(tool, "args_schema", None)

    async def ainvoke(self, input: Any, config: Any = None) -> Any:
        """Execute tool, routing through Sidecar if configured."""
        from app.core.context.manager import ContextManager

        ctx = ContextManager.current()
        thread_id = ctx.thread_id if ctx else "unknown"

        if should_use_sidecar(self.name):
            # Convert input to params dict
            if isinstance(input, dict):
                params = input
            else:
                params = {"input": input}

            logger.info(f"[SidecarToolWrapper] Routing {self.name} via Sidecar")
            return await execute_via_sidecar(thread_id, self.name, params)
        else:
            # Execute locally using original tool
            return await self._tool.ainvoke(input, config)

    def __getattr__(self, name: str):
        """Delegate attribute access to wrapped tool."""
        return getattr(self._tool, name)


def wrap_tools_for_sidecar(tools: list[Any]) -> list[Any]:
    """
    Wrap a list of tools for Sidecar execution.

    Args:
        tools: List of LangChain tools

    Returns:
        List of wrapped tools
    """
    if not settings.USE_SIDECAR_FOR_TOOLS:
        return tools

    wrapped = []
    for tool in tools:
        if should_use_sidecar(tool.name):
            wrapped.append(SidecarToolWrapper(tool))
        else:
            wrapped.append(tool)

    return wrapped
