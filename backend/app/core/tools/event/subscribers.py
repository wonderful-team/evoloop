"""
Tool Module Lifecycle Handlers
Handles eager discovery and registration of all @evoloop_tool decorated tools
on application startup.
"""
import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class ToolsLifecycleHandler:
    """
    Handles lifecycle events for the Tool system.

    On APP_STARTED, eagerly scans and registers all native tools so that
    the registry is warm before the first request.
    """

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Handle APP_STARTED: Eagerly scan packages and register all tools.
        """
        logger.info("[Tools] 🔧 Scanning and registering tools...")

        from app.core.tools.registry import _ensure_scanned, get_all_tools

        _ensure_scanned()
        registered_tools = get_all_tools()

        logger.info(f"[Tools] ✓ Registered {len(registered_tools)} tool(s)")
