"""
MCP (Model Context Protocol) Module Lifecycle Handlers
Handles connection initialization and global client cleanup.
"""
import logging
from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class McpLifecycleHandler:
    """
    Handles initialization and graceful shutdown of MCP clients.
    """

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Handle APP_STARTED: Initialize/Register configured MCP servers.
        """
        try:
            from app.core.mcp.registrar import init_mcp
            
            logger.info("[MCP] 🔌 Initializing MCP Servers...")
            mcp_results = await init_mcp()
            logger.info(f"[MCP] ✓ Servers initialized: {len(mcp_results)}")
        except Exception as e:
            logger.error(f"[MCP] Initialization failed: {e}")

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
            logger.warning(f"[MCP] Cleanup failed: {e}")
