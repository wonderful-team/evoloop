"""
Environment Module Lifecycle Handlers
Handles application-level startup and shutdown events.
"""
import logging
from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class EnvironmentLifecycleHandler:
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
        try:
            from app.core.environment import awaken
            from app.core.environment.controllers.device_watcher import device_watcher
            
            # 1. Awaken Agent
            logger.info("[Environment] 🌅 Triggering Agent Awakening...")
            await awaken()
            logger.info("[Environment] ✓ Agent awakening process complete")
            
            # 2. Start Device Watcher
            logger.info("[Environment] 🔍 Starting Device Watcher...")
            device_watcher.start()
            logger.info("[Environment] ✓ Device Watcher started")
        except Exception as e:
            logger.error(f"[Environment] Failed to complete awakening/watcher startup: {e}")

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        """
        Handle APP_STOPPING event:
        1. Stop Device Watcher
        2. Cleanup all active mirror sessions
        """
        try:
            from app.core.environment.controllers.device_watcher import device_watcher
            from app.core.environment.controllers.mirror_session import mirror_manager
            
            # 1. Stop Watcher
            device_watcher.stop()
            logger.info("[Environment] Device Watcher stopped")
            
            # 2. Cleanup Mirrors (Sync)
            mirror_manager.cleanup()
            logger.info("[Environment] All mirror sessions and containers cleaned up")
        except Exception as e:
            logger.warning(f"[Environment] Cleanup errors during shutdown: {e}")
