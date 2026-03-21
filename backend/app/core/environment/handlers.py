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

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class DeviceEventHandler:
    """Handles device connection/disconnection events"""

    @staticmethod
    async def on_device_connected(event: AwakenEvent) -> None:
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

    @staticmethod
    async def on_device_disconnected(event: AwakenEvent) -> None:
        """
        Handle device disconnection - refresh state.
        
        Triggered when an Android device disconnects.
        """
        device_id = event.data.get("device_id")
        logger.info(f"🔌 Device disconnected: {device_id}")

        from app.core.environment import _refresh_state
        await _refresh_state()


class SkillEventHandler:
    """Handles skill execution events for skill evolution"""

    @staticmethod
    async def on_skill_executed(event: AwakenEvent) -> None:
        """
        Log skill execution for monitoring and analytics.
        
        This handler can be extended for analytics, dashboards, etc.
        """
        skill_name = event.data.get("skill_name")
        success = event.data.get("success")
        confidence_delta = event.data.get("confidence_delta", 0)

        if success:
            logger.info(f"✅ Skill executed: {skill_name} (confidence +{confidence_delta})")
        else:
            logger.warning(f"❌ Skill failed: {skill_name} (confidence {confidence_delta})")

    @staticmethod
    async def on_skill_promoted(event: AwakenEvent) -> None:
        """
        Handle skill promotion events.
        
        Logs when a skill advances in status (draft -> candidate -> verified).
        """
        skill_name = event.data.get("skill_name")
        old_status = event.data.get("old_status")
        new_status = event.data.get("new_status")
        logger.info(f"🎓 Skill promoted: {skill_name} ({old_status} -> {new_status})")

    @staticmethod
    async def on_skill_deprecated(event: AwakenEvent) -> None:
        """
        Handle skill deprecation events.
        
        Logs when a skill is marked as deprecated due to repeated failures.
        """
        skill_name = event.data.get("skill_name")
        reason = event.data.get("reason", "repeated failures")
        logger.warning(f"⚠️ Skill deprecated: {skill_name} - {reason}")


class SystemEventHandler:
    """Handles system-level awakening events"""

    @staticmethod
    async def on_awakening_complete(event: AwakenEvent) -> None:
        """
        Log awakening completion.
        
        Triggered after the full awakening process completes.
        """
        platforms = event.data.get("platforms", [])
        project_id = event.data.get("project_id")
        logger.info(f"🧠 Awakening complete. Platforms: {platforms}, Project: {project_id}")

    @staticmethod
    async def on_state_refreshed(event: AwakenEvent) -> None:
        """
        Log state refresh.
        
        Triggered when AwakenedState is updated.
        """
        trigger = event.data.get("trigger", "unknown")
        logger.debug(f"🔄 State refreshed (trigger: {trigger})")

    @staticmethod
    async def on_boundary_learned(event: AwakenEvent) -> None:
        """
        Log when a new dynamic boundary is learned.
        
        Triggered by AdaptiveBoundaryManager on tool failures.
        """
        tool_name = event.data.get("tool_name")
        category = event.data.get("category")
        description = event.data.get("description")
        logger.info(f"🚧 New boundary learned [{category}]: {description}")


class AppAtlasEventHandler:
    """Handles spatial mapping events."""

    @staticmethod
    async def on_ui_tree_observed(event: AwakenEvent) -> None:
        """
        Background processing of UI trees into the Neo4j App Atlas.
        """
        from app.core.atlas import atlas_engine
        await atlas_engine.on_ui_tree_observed(event)


def register_default_handlers() -> None:
    """
    Register all default event handlers with the event bus.
    
    Should be called during application startup (in main.py lifespan).
    """
    if event_bus.is_initialized:
        logger.debug("Event handlers already registered, skipping")
        return

    # Device events
    event_bus.subscribe(EventType.DEVICE_CONNECTED, DeviceEventHandler.on_device_connected)
    event_bus.subscribe(EventType.DEVICE_DISCONNECTED, DeviceEventHandler.on_device_disconnected)

    # Skill events
    event_bus.subscribe(EventType.SKILL_EXECUTED, SkillEventHandler.on_skill_executed)
    event_bus.subscribe(EventType.SKILL_PROMOTED, SkillEventHandler.on_skill_promoted)
    event_bus.subscribe(EventType.SKILL_DEPRECATED, SkillEventHandler.on_skill_deprecated)

    # System events
    event_bus.subscribe(EventType.AWAKENING_COMPLETE, SystemEventHandler.on_awakening_complete)
    event_bus.subscribe(EventType.STATE_REFRESHED, SystemEventHandler.on_state_refreshed)
    event_bus.subscribe(EventType.BOUNDARY_LEARNED, SystemEventHandler.on_boundary_learned)

    # App Atlas events - DISABLED: Passive learning removed to reduce overhead
    # Atlas query functionality remains available via query_app_atlas tool
    # event_bus.subscribe(EventType.UI_TREE_OBSERVED, AppAtlasEventHandler.on_ui_tree_observed)

    event_bus.mark_initialized()
    logger.info("📡 Awakening event handlers registered")
