"""
Generic Client Proxy - Universal proxy for all local tool execution.

This module provides a unified interface for Backend to execute ANY local tool
via the Client process. Replaces specialized proxies (file_proxy, shell_proxy, etc.)

Supported tools (delegated to Client):
    - file_read, file_write, file_list, file_delete
    - shell, shell_batch
    - adb_connect, adb_shell, adb_screenshot, adb_swipe, adb_tap
    - browser_navigate, browser_click, browser_screenshot
    - desktop_screenshot, desktop_click, desktop_type
    - mcp (MCP tool calls)

Usage:
    from app.infrastructure.client import client_proxy

    # Execute any tool
    result = await client_proxy.execute(
        thread_id="thread-1",
        tool="shell",
        params={"command": "ls -la", "cwd": "/tmp"}
    )

    # Or use the global executor directly
    from app.infrastructure.client import get_executor
    executor = get_executor()
    result = await executor.execute("thread-1", "file_read", {"path": "/etc/hosts"})

Performance:
    Automatically selects the best available transport:
    1. WebSocket (lowest latency, if connected)
    2. HTTP callback (fallback)
"""

import logging
from typing import Any

from app.core.config import settings
from app.infrastructure.client.http import ClientToolExecutor, ToolExecutionError
from app.infrastructure.client.websocket import (
    DirectClientToolExecutor,
    client_ws_manager,
)

logger = logging.getLogger(__name__)


class ClientProxy:
    """
    Universal proxy for executing local tools via Client.

    This is the single entry point for ALL local tool execution when running
    in CLOUD_ONLY_MODE. Supports file, shell, ADB, browser, desktop, MCP tools.
    """

    def __init__(self):
        self._http_executor: ClientToolExecutor | None = None
        self._ws_executor: DirectClientToolExecutor | None = None

    def _get_executor(self) -> Any:
        """Get the best available executor."""
        # Prefer WebSocket for lower latency
        if self._ws_executor is None:
            self._ws_executor = DirectClientToolExecutor()

        # Check if WebSocket is actually connected
        if client_ws_manager.is_connected():
            return self._ws_executor

        logger.debug("[ClientProxy] WebSocket not connected, using HTTP fallback")

        # Fallback to HTTP
        if self._http_executor is None:
            self._http_executor = ClientToolExecutor()
        return self._http_executor

    async def execute(
        self,
        thread_id: str,
        tool: str,
        params: dict[str, Any],
        timeout: float = 300.0
    ) -> Any:
        """
        Execute any tool via Client.

        Args:
            thread_id: Conversation thread ID for tracking
            tool: Tool name (file_read, shell, adb_connect, browser_navigate, etc.)
            params: Tool-specific parameters
            timeout: Maximum execution time in seconds

        Returns:
            Tool execution result (type varies by tool)

        Raises:
            ToolExecutionError: If execution fails or times out
            ConnectionError: If Client is not available

        Examples:
            # File operations
            content = await client_proxy.execute("t1", "file_read", {"path": "/etc/hosts"})

            # Shell command
            result = await client_proxy.execute("t1", "shell", {
                "command": "docker ps",
                "cwd": "/home/user"
            })

            # ADB
            await client_proxy.execute("t1", "adb_connect", {"device_id": "abc123"})

            # Browser
            await client_proxy.execute("t1", "browser_navigate", {"url": "https://example.com"})

            # MCP
            result = await client_proxy.execute("t1", "mcp", {
                "server": "filesystem",
                "tool": "read_file",
                "arguments": {"path": "/etc/hosts"}
            })
        """
        if not settings.CLOUD_ONLY_MODE:
            # In local mode, tools should execute directly
            raise RuntimeError(
                "ClientProxy should only be used in CLOUD_ONLY_MODE. "
                "In local mode, execute tools directly."
            )

        executor = self._get_executor()

        try:
            return await executor.execute(
                thread_id=thread_id,
                tool=tool,
                params=params,
                timeout=timeout
            )
        except ToolExecutionError:
            raise
        except Exception as e:
            logger.exception(f"[ClientProxy] Tool execution failed: {e}")
            raise ToolExecutionError(str(e))

    # ============== Convenience methods for common tools ==============
    # These are optional shortcuts, execute() can handle all cases

    async def file_read(self, path: str, encoding: str = "utf-8", thread_id: str = "default") -> str:
        """Read file via Client."""
        return await self.execute(thread_id, "file_read", {"path": path, "encoding": encoding})

    async def file_write(self, path: str, content: str, encoding: str = "utf-8", thread_id: str = "default") -> dict:
        """Write file via Client."""
        return await self.execute(thread_id, "file_write", {
            "path": path, "content": content, "encoding": encoding
        })

    async def file_list(self, path: str, thread_id: str = "default") -> list[dict]:
        """List directory via Client."""
        return await self.execute(thread_id, "file_list", {"path": path})

    async def shell(self, command: str, cwd: str | None = None, timeout: int = 60, thread_id: str = "default") -> dict:
        """Execute shell command via Client."""
        params = {"command": command, "timeout": timeout}
        if cwd:
            params["cwd"] = cwd
        return await self.execute(thread_id, "shell", params, timeout=timeout + 10)

    async def adb_shell(self, device_id: str, command: str, thread_id: str = "default") -> str:
        """Execute ADB shell command via Client."""
        return await self.execute(thread_id, "adb_shell", {"device_id": device_id, "command": command})

    async def browser_navigate(self, url: str, thread_id: str = "default") -> dict:
        """Navigate browser via Client."""
        return await self.execute(thread_id, "browser_navigate", {"url": url})

    async def mcp_call(self, server: str, tool: str, arguments: dict, thread_id: str = "default") -> Any:
        """Call MCP tool via Client."""
        return await self.execute(thread_id, "mcp", {
            "server": server, "tool": tool, "arguments": arguments
        })


def get_executor() -> Any:
    """Get the appropriate executor (WebSocket or HTTP)."""
    if client_ws_manager.is_connected():
        return DirectClientToolExecutor()
    return ClientToolExecutor()


def is_proxy_required() -> bool:
    """Check if Client proxy is required (i.e., running in cloud-only mode)."""
    return settings.CLOUD_ONLY_MODE


# Global instance
client_proxy = ClientProxy()
