"""
Atlas Module Lifecycle Handlers
Handles global configuration synchronization on application start.
"""
import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class AtlasLifecycleSubscriber:
    """
    Handles synchronization of Atlas configuration on application events.
    """

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Handle APP_STARTED: Synchronize Atlas YAML configuration.
        """
        logger.info("[Atlas] 🗺️ Synchronizing Atlas configuration...")
        await init_atlas_config()
        logger.info("[Atlas] ✓ Configuration synchronized")


async def init_atlas_config() -> None:
    """Initialize Atlas configuration (Cache-based, no hardcoding)."""
    logger.info("Initializing Atlas configuration...")
    from app.core.atlas.config_manager import AtlasConfigManager
    await AtlasConfigManager.initialize_defaults()
