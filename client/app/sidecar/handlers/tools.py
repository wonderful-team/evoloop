"""
Tool execution handlers for Sidecar protocol.

Handles requests from Tauri to execute local tools.
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

from app.core.context import thread_context_store
from app.core.tools.mcp.client import mcp_client_manager

logger = logging.getLogger(__name__)


async def handle_execute(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool request from Tauri.

    Args:
        message: {
            "type": "execute",
            "id": "req-1",
            "tool": "file_read" | "file_write" | "shell" | "mcp",
            "params": {...}
        }

    Returns:
        {"result": ..., "error": null} or {"error": ...}
    """
    tool_name = message.get("tool")
    params = message.get("params", {})

    logger.info(f"Executing tool: {tool_name} with params: {params}")

    try:
        if tool_name == "file_read":
            result = await _handle_file_read(params)
        elif tool_name == "file_write":
            result = await _handle_file_write(params)
        elif tool_name == "file_list":
            result = await _handle_file_list(params)
        elif tool_name == "shell":
            result = await _handle_shell(params)
        elif tool_name == "mcp":
            result = await _handle_mcp(params)
        elif tool_name == "get_context":
            result = await _handle_get_context(params)
        else:
            return {"error": f"Unknown tool: {tool_name}"}

        return {"result": result, "error": None}

    except Exception as e:
        logger.error(f"Tool execution error: {e}", exc_info=True)
        return {"error": str(e)}


async def handle_ping(message: Dict[str, Any]) -> Dict[str, Any]:
    """Simple ping/pong for health check."""
    return {"pong": True}


async def _handle_file_read(params: Dict[str, Any]) -> str:
    """Read file contents."""
    path = params.get("path")
    if not path:
        raise ValueError("path is required")

    # Security: check if path is allowed
    path = os.path.expanduser(path)
    if not _is_path_allowed(path):
        raise PermissionError(f"Access denied: {path}")

    encoding = params.get("encoding", "utf-8")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _read_file_sync, path, encoding)


def _read_file_sync(path: str, encoding: str) -> str:
    """Synchronous file read."""
    with open(path, "r", encoding=encoding, errors="replace") as f:
        return f.read()


async def _handle_file_write(params: Dict[str, Any]) -> Dict[str, Any]:
    """Write file contents."""
    path = params.get("path")
    content = params.get("content")

    if not path or content is None:
        raise ValueError("path and content are required")

    path = os.path.expanduser(path)
    if not _is_path_allowed(path):
        raise PermissionError(f"Access denied: {path}")

    # Create parent directories if needed
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

    encoding = params.get("encoding", "utf-8")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _write_file_sync, path, content, encoding)

    return {"written": True, "path": path, "bytes": len(content.encode(encoding))}


def _write_file_sync(path: str, content: str, encoding: str) -> None:
    """Synchronous file write."""
    with open(path, "w", encoding=encoding) as f:
        f.write(content)


async def _handle_file_list(params: Dict[str, Any]) -> list:
    """List directory contents."""
    path = params.get("path", ".")
    path = os.path.expanduser(path)

    if not _is_path_allowed(path):
        raise PermissionError(f"Access denied: {path}")

    if not os.path.exists(path):
        raise FileNotFoundError(f"Path not found: {path}")

    if not os.path.isdir(path):
        raise NotADirectoryError(f"Not a directory: {path}")

    entries = []
    for entry in os.listdir(path):
        full_path = os.path.join(path, entry)
        entries.append({
            "name": entry,
            "path": full_path,
            "type": "directory" if os.path.isdir(full_path) else "file",
            "size": os.path.getsize(full_path) if os.path.isfile(full_path) else None,
        })

    return entries


async def _handle_shell(params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute shell command."""
    command = params.get("command")
    if not command:
        raise ValueError("command is required")

    cwd = params.get("cwd")
    timeout = params.get("timeout", 60)
    env = params.get("env")

    # Use working directory if specified
    if cwd:
        cwd = os.path.expanduser(cwd)
        if not _is_path_allowed(cwd):
            raise PermissionError(f"Access denied for cwd: {cwd}")

    logger.info(f"Executing shell: {command[:100]}...")

    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env={**os.environ, **env} if env else None
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode,
            "success": proc.returncode == 0
        }
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError(f"Command timed out after {timeout}s")


async def _handle_mcp(params: Dict[str, Any]) -> Any:
    """Execute MCP tool."""
    server = params.get("server")
    tool = params.get("tool")
    arguments = params.get("arguments", {})

    if not server or not tool:
        raise ValueError("server and tool are required")

    if not mcp_client_manager.is_connected(server):
        raise ConnectionError(f"MCP server '{server}' not connected")

    result = await mcp_client_manager.call_tool(server, tool, arguments)
    return result


async def _handle_get_context(params: Dict[str, Any]) -> Dict[str, Any]:
    """Get current thread context."""
    thread_id = params.get("thread_id", "default")
    return {
        "working_directory": thread_context_store.get_working_directory(thread_id),
        "session_id": thread_context_store.get_session_id(thread_id),
    }


def _is_path_allowed(path: str) -> bool:
    """
    Check if a path is allowed for file operations.

    For now, allow all paths within WORKSPACE_ROOT or user's home.
    In production, this should be more restrictive.
    """
    from app.core.config import settings
    from app.infrastructure.config import SystemConfigService

    path = os.path.abspath(path)

    # Get allowed roots
    workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT") or settings.WORKSPACE_ROOT
    home_dir = os.path.expanduser("~")

    allowed_roots = []
    if workspace_root:
        allowed_roots.append(os.path.abspath(workspace_root))
    allowed_roots.append(home_dir)

    # Also allow /tmp for temporary operations
    allowed_roots.append("/tmp")

    for root in allowed_roots:
        try:
            if path.startswith(root):
                return True
        except ValueError:
            # On Windows, different drives can cause ValueError
            pass

    logger.warning(f"Path access denied: {path}, allowed roots: {allowed_roots}")
    return False
