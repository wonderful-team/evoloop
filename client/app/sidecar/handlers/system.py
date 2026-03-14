"""
System handlers for Sidecar protocol.

Handles initialization, shutdown, and status requests.
"""

import logging
from typing import Any, Dict

from app.core.config import settings
from app.core.tools.mcp.client import mcp_client_manager
from app.infrastructure.config import SystemConfigService

logger = logging.getLogger(__name__)


async def handle_init(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle initialization request from Tauri.

    Args:
        message: {
            "type": "init",
            "workspace_root": "/path/to/workspace",  # optional override
            "config": {...}  # optional config overrides
        }

    Returns:
        {"initialized": True, "capabilities": [...]}
    """
    try:
        # Update workspace root if provided
        workspace_root = message.get("workspace_root")
        if workspace_root:
            SystemConfigService.set_value("WORKSPACE_ROOT", workspace_root)
            logger.info(f"Workspace root set to: {workspace_root}")

        # Apply other config if provided
        config = message.get("config", {})
        for key, value in config.items():
            SystemConfigService.set_value(key, value)

        # Initialize MCP if needed
        mcp_results = {}
        try:
            from app.initial_data import init_mcp
            mcp_results = await init_mcp()
        except Exception as e:
            logger.warning(f"MCP init during sidecar init: {e}")

        return {
            "initialized": True,
            "capabilities": [
                "file_read",
                "file_write",
                "file_list",
                "shell",
                "mcp",
                "get_context",
            ],
            "workspace_root": SystemConfigService.get_value("WORKSPACE_ROOT") or settings.WORKSPACE_ROOT,
            "mcp_servers": list(mcp_client_manager.sessions.keys()) if hasattr(mcp_client_manager, 'sessions') else [],
        }

    except Exception as e:
        logger.error(f"Initialization error: {e}", exc_info=True)
        return {"initialized": False, "error": str(e)}


async def handle_shutdown(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle graceful shutdown request.

    Args:
        message: {"type": "shutdown"}

    Returns:
        {"shutdown": True}
    """
    from app.sidecar.protocol import get_protocol

    logger.info("Shutdown requested from Tauri")

    # Signal shutdown
    await get_protocol().stop()

    return {"shutdown": True}


async def handle_status(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get current status.

    Args:
        message: {"type": "status"}

    Returns:
        {"status": "ready", "active_threads": [...], "mcp_status": {...}}
    """
    try:
        mcp_status = {}
        if hasattr(mcp_client_manager, 'sessions'):
            for name in mcp_client_manager.sessions:
                mcp_status[name] = "connected"

        return {
            "status": "ready",
            "workspace_root": SystemConfigService.get_value("WORKSPACE_ROOT") or settings.WORKSPACE_ROOT,
            "mcp_servers": mcp_status,
        }

    except Exception as e:
        logger.error(f"Status error: {e}")
        return {"status": "error", "error": str(e)}
