"""
Atlas Module Lifecycle Handlers
Handles global configuration synchronization on application start.
"""
import logging
from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class AtlasLifecycleHandler:
    """
    Handles synchronization of Atlas configuration on application events.
    """

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Handle APP_STARTED: Synchronize Atlas YAML configuration.
        """
        try:
            from app.core.atlas.initial_data import init_atlas_config
            
            logger.info("[Atlas] 🗺️ Synchronizing Atlas configuration...")
            await init_atlas_config()
            logger.info("[Atlas] ✓ Configuration synchronized")
        except Exception as e:
            logger.error(f"[Atlas] Synchronization failed: {e}")
