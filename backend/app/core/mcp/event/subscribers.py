"""
MCP (Model Context Protocol) Module Lifecycle Handlers
Handles connection initialization and global client cleanup.
"""

import json
import logging

from sqlalchemy import select

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.infrastructure.database import session_scope
from app.models import McpServer

logger = logging.getLogger(__name__)


@event_register()
class McpLifecycleSubscriber:
    """
    Handles initialization and graceful shutdown of MCP clients.
    """

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Handle APP_STARTED: Initialize/Register configured MCP servers, then
        connect to all enabled ones so their tools are injected into Agent runs.
        """
        logger.info("[MCP] 🔌 Initializing MCP Servers...")
        mcp_results = await init_mcp()

        from app.core.mcp import mcp_client_manager

        connect_results = await mcp_client_manager.connect_all()
        connected = sum(1 for r in connect_results if r.success)
        logger.info(
            "[MCP] ✓ Servers initialized: %d, connected: %d/%d",
            len(mcp_results),
            connected,
            len(connect_results),
        )

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        """
        Handle APP_STOPPING: Disconnect and cleanup all active MCP clients.
        """
        try:
            from app.core.mcp import mcp_client_manager

            await mcp_client_manager.disconnect_all()
            logger.info("[MCP] All clients disconnected")
        except Exception as e:
            logger.warning(f"[MCP] Cleanup failed: {e}", exc_info=True)

    @event_subscribe(SystemEventType.CONFIG_CHANGED)
    async def on_config_changed(self, event):
        """
        Handle CONFIG_CHANGED: Respond to configuration updates.
        """
        key = event.data.get("key")
        new_value = event.data.get("new_value")

        if key == "WORKSPACE_ROOT":
            logger.info(f"[MCP] WORKSPACE_ROOT changed to {new_value}, reloading filesystem MCP...")
            await reload_mcp_for_workspace_change()


async def init_mcp(force_update: bool = False) -> dict[str, str]:
    """
    Initialize MCP server configurations.

    This function ONLY adds server configs to DB, it does NOT connect.
    Connection happens later via mcp_client_manager.connect_all().

    Args:
        force_update: Deprecated; kept for signature compatibility.

    Returns:
        Dict of configured server names and their status.
    """
    del force_update  # 默认 server 已移除，该参数不再影响行为（兼容旧调用方）
    logger.info("Initializing MCP configuration...")
    results = {}

    # Check existing servers in DB (not connected sessions)
    async with session_scope() as session:
        result = await session.execute(select(McpServer.name))
        existing_db_servers = {row[0] for row in result.all()}

    # MCP servers are now managed exclusively via DB configuration
    # (McpServer table). Default npx-based servers (local-postgres / filesystem /
    # brave-search) are no longer auto-seeded; they caused npx download stalls
    # and polluted Agent tool lists.
    for name in existing_db_servers:
        results[name] = "skipped_existing"

    return results


async def reload_mcp_for_workspace_change() -> dict[str, str]:
    """
    Reconfigure MCP servers when WORKSPACE_ROOT changes at runtime.

    Only filesystem MCP needs to be reconfigured.

    Returns:
        Dict of server names and their status
    """
    logger.info("Reloading MCP configuration due to WORKSPACE_ROOT change...")
    results = {}

    # 1. Update DB config (init_mcp handles path check and DB update)
    db_result = await init_mcp(force_update=True)
    results["db_update"] = db_result

    # 2. Disconnect and reconnect filesystem MCP
    try:
        from app.core.mcp import mcp_client_manager

        # Disconnect existing if connected
        if "filesystem" in mcp_client_manager.sessions:
            logger.info("Disconnecting existing filesystem MCP...")
            # remove_server handles both disconnect and cleanup
            await mcp_client_manager.remove_server("filesystem")
            results["disconnect"] = "success"
        else:
            results["disconnect"] = "not_connected"

        # Reconnect (will load new config from DB)
        logger.info("Reconnecting filesystem MCP...")
        connected = await mcp_client_manager.ensure_connected("filesystem")
        results["reconnect"] = "success" if connected else "failed"

    except Exception as e:
        logger.exception(f"Failed to reload MCP for workspace change: {e}")
        results["error"] = str(e)

    return results
