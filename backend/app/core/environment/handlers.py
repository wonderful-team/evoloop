"""
Awakening Event Handlers

Default handlers for the awakening event bus.
Each handler responds to specific event types and triggers appropriate actions.
"""

import logging
from typing import TYPE_CHECKING

from app.core.environment.events import (
    AwakenEvent,
    EventType,
    event_bus,
)
from app.core.events.decorators import event_register_with_bus, event_subscribe

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@event_register_with_bus(event_bus)
class DeviceEventHandler:
    """Handles device connection/disconnection events"""

    def __init__(self):
        pass

    @event_subscribe(EventType.DEVICE_CONNECTED)
    async def on_device_connected(self, event: AwakenEvent) -> None:
        """
        Handle device connection - refresh state and probe new apps.
        
        Triggered when a new Android device is connected via ADB.
        """
        device_id = event.data.get("device_id")
        device_type = event.data.get("device_type", "android")

        logger.info(f"🔌 Device connected: {device_id} ({device_type})")

        # Refresh awakened state
        from app.core.environment import _refresh_state
        await _refresh_state()

        # Trigger app probing for new Android devices
        if device_type == "android":
            from app.core.environment import get_awakened_state
            from app.core.environment.explorers.android import AndroidExplorer

            state = get_awakened_state()
            if state and state.android_devices:
                device = next((d for d in state.android_devices if d.device_id == device_id), None)
                if device:
                    logger.info(f"📱 Probing apps on device: {device_id}")
                    try:
                        explorer = AndroidExplorer()
                        await explorer.scan(device_id)
                    except Exception as e:
                        logger.warning(f"Failed to probe device {device_id}: {e}")

    @event_subscribe(EventType.DEVICE_DISCONNECTED)
    async def on_device_disconnected(self, event: AwakenEvent) -> None:
        """
        Handle device disconnection - refresh state.
        
        Triggered when an Android device disconnects.
        """
        device_id = event.data.get("device_id")
        logger.info(f"🔌 Device disconnected: {device_id}")

        from app.core.environment import _refresh_state
        await _refresh_state()


@event_register_with_bus(event_bus)
class SkillEventHandler:
    """Handles skill execution events for skill evolution"""

    def __init__(self):
        pass

    @event_subscribe(EventType.SKILL_EXECUTED)
    async def on_skill_executed(self, event: AwakenEvent) -> None:
        """
        Log skill execution for monitoring and analytics.
        
        This handler can be extended for analytics, dashboards, etc.
        """
        skill_name = event.data.get("skill_name")
        thread_id = event.data.get("thread_id")
        
        logger.debug(f"🎯 Skill executed: {skill_name} in thread {thread_id}")

    @event_subscribe(EventType.SKILL_PROMOTED)
    async def on_skill_promoted(self, event: AwakenEvent) -> None:
        """
        Handle skill promotion to built-in status.
        
        Triggered when a learned skill is promoted to built-in.
        """
        skill_name = event.data.get("skill_name")
        
        logger.info(f"⭐ Skill promoted to built-in: {skill_name}")

    @event_subscribe(EventType.SKILL_DEPRECATED)
    async def on_skill_deprecated(self, event: AwakenEvent) -> None:
        """
        Handle skill deprecation.
        
        Triggered when a skill is deprecated (replaced or outdated).
        """
        skill_name = event.data.get("skill_name")
        reason = event.data.get("reason", "No reason provided")
        
        logger.info(f"🗑️ Skill deprecated: {skill_name} - {reason}")


@event_register_with_bus(event_bus)
class SystemEventHandler:
    """Handles system-level awakening events"""

    def __init__(self):
        pass

    @event_subscribe(EventType.AWAKENING_COMPLETE)
    async def on_awakening_complete(self, event: AwakenEvent) -> None:
        """
        Handle awakening completion.
        
        Triggered when the agent awakening process is complete.
        """
        platforms = event.data.get("platforms", [])
        project = event.data.get("project")
        
        logger.info(f"🧠 Awakening complete. Platforms: {platforms}, Project: {project}")

    @event_subscribe(EventType.STATE_REFRESHED)
    async def on_state_refreshed(self, event: AwakenEvent) -> None:
        """
        Handle state refresh.
        
        Triggered when the awakened state is manually refreshed.
        """
        logger.debug("🔄 Awakened state refreshed")

    @event_subscribe(EventType.BOUNDARY_LEARNED)
    async def on_boundary_learned(self, event: AwakenEvent) -> None:
        """
        Handle learned boundary.
        
        Triggered when the agent learns a new platform boundary (e.g., auth wall).
        """
        platform = event.data.get("platform")
        boundary_type = event.data.get("boundary_type")
        
        logger.info(f"🚧 Learned boundary: {boundary_type} on {platform}")


# App Atlas event handler - DISABLED: Passive learning removed to reduce overhead
# Atlas query functionality remains available via query_app_atlas tool
# @event_register_with_bus(event_bus)
# class AppAtlasEventHandler:
#     """Handles UI tree observation events for App Atlas"""
# 
#     def __init__(self):
#         pass
# 
#     @event_subscribe(EventType.UI_TREE_OBSERVED)
#     async def on_ui_tree_observed(self, event: AwakenEvent) -> None:
#         """
#         Process UI tree for App Atlas learning.
#         
#         Triggered when a UI tree is observed (e.g., from screenshot analysis).
#         """
#         from app.core.atlas import atlas_engine
#         await atlas_engine.on_ui_tree_observed(event)


def register_default_handlers() -> None:
    """
    Register all default event handlers with the event bus.
    
    Note: With @event_register_with_bus() decorator, handlers are auto-registered on import.
    This function is kept for backward compatibility and to prevent double registration.
    """
    if event_bus.is_initialized:
        logger.debug("Event handlers already registered, skipping")
        return

    # Instantiate handlers to trigger auto-registration
    DeviceEventHandler()
    SkillEventHandler()
    SystemEventHandler()
    # AppAtlasEventHandler()  # Disabled

    event_bus.mark_initialized()
    logger.info("📡 Awakening event handlers registered")
