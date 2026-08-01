"""
Environment Event Subscribers
=============================

Event subscribers for the Awakening/Environment domain.
"""
import asyncio
import logging

from app.core.environment.event.types import EventType
from app.core.events.decorators import (
    event_register,
    event_subscribe,
)
from app.core.events.registry import SystemEventType

from .schemas import (
    AwakenEvent,
    DeviceConnectedEvent,
    DeviceDisconnectedEvent,
)

logger = logging.getLogger(__name__)

_background_tasks = set()


@event_register()
class EnvironmentLifecycleSubscriber:
    """
    Handles application-level lifecycle events for the Environment domain.

    Includes:
    - Agent Awakening (probe & context hydration) on app start
    - Device Watcher initialization on app start
    - Final state persistent and resource cleanup on app stop
    """

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Handle APP_STARTED event:
        1. Trigger Agent Awakening (Environment Probe, Memory Replay, Pref Priming)
        2. Start Device Watcher for Android devices
        """
        from app.core.environment import awaken
        from app.core.environment.controllers.device_watcher import device_watcher

        # 1. Awaken Agent
        logger.info("[Environment] 🌅 Scheduling Agent Awakening in background...")
        import asyncio
        task = asyncio.create_task(awaken())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

        # 2. Start Device Watcher
        logger.info("[Environment] 🔍 Starting Device Watcher...")
        device_watcher.start()
        logger.info("[Environment] ✓ Device Watcher started")

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        """
        Handle APP_STOPPING event:
        1. Stop Device Watcher
        2. Cleanup all active mirror sessions
        3. Cancel any pending background tasks (awaken + dynamic triage)
        """
        try:
            from app.core.environment.controllers.device_watcher import device_watcher
            from app.core.environment.controllers.mirror_session import mirror_manager
            from app.core.environment.discovery import cancel_dynamic_triage_tasks

            # 1. Stop Watcher
            device_watcher.stop()
            logger.info("[Environment] Device Watcher stopped")

            # 2. Cleanup Mirrors (Sync)
            mirror_manager.cleanup()
            logger.info("[Environment] All mirror sessions and containers cleaned up")

            # 3. Cancel pending background tasks
            await cancel_dynamic_triage_tasks()
            for task in list(_background_tasks):
                if task.done():
                    continue
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            _background_tasks.clear()
            logger.info("[Environment] Background tasks cancelled")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[Environment] Cleanup errors during shutdown: {e}")


@event_register()
class DeviceEventSubscriber:
    """Handles device connection/disconnection events"""

    @event_subscribe(EventType.DEVICE_CONNECTED)
    async def on_device_connected(self, event: "DeviceConnectedEvent") -> None:
        """
        Handle device connection - refresh state and probe new apps.

        Triggered when a new Android device is connected via ADB.
        """
        device_id = event.device_id
        device_type = event.device_type

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
                    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                        logger.warning(f"Failed to probe device {device_id}: {e}")

    @event_subscribe(EventType.DEVICE_DISCONNECTED)
    async def on_device_disconnected(self, event: "DeviceDisconnectedEvent") -> None:
        """
        Handle device disconnection - refresh state.

        Triggered when an Android device disconnects.
        """
        device_id = event.device_id
        logger.info(f"🔌 Device disconnected: {device_id}")

        from app.core.environment import _refresh_state
        await _refresh_state()


@event_register()
class SkillEventSubscriber:
    """Handles skill execution events for skill evolution"""

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


@event_register()
class SystemEventSubscriber:
    """Handles system-level awakening events"""

    @event_subscribe(SystemEventType.AWAKENING_COMPLETE)
    async def on_awakening_complete(self, event: AwakenEvent) -> None:
        """
        Handle awakening completion.

        Triggered when the agent awakening process is complete.
        """
        platforms = event.data.get("platforms", [])
        project = event.data.get("project")

        logger.info(f"🧠 Awakening complete. Platforms: {platforms}, Project: {project}")

    @event_subscribe(SystemEventType.STATE_REFRESHED)
    async def on_state_refreshed(self, event: AwakenEvent) -> None:
        """
        Handle state refresh.

        Triggered when the awakened state is manually refreshed.
        """
        logger.debug("🔄 Awakened state refreshed")

    @event_subscribe(SystemEventType.BOUNDARY_LEARNED)
    async def on_boundary_learned(self, event: AwakenEvent) -> None:
        """
        Handle learned boundary.

        Triggered when the agent learns a new platform boundary (e.g., auth wall).
        """
        platform = event.data.get("platform")
        boundary_type = event.data.get("boundary_type")

        logger.info(f"🚧 Learned boundary: {boundary_type} on {platform}")
