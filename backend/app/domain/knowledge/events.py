"""
Knowledge Module Event Handlers
"""
import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class KnowledgeLifecycleHandler:
    """
    Handles knowledge-related system events.
    
    Includes:
    - Initializing extractor registry
    - Initializing FTS search services
    - Initializing citation trackers
    """

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Handle APP_STARTED event:
        1. Initialize Knowledge Base Extractors
        2. Initialize FTS (Full Text Search) index
        3. Initialize Citation Tracker
        """
        # 1. Extractor Registry
        try:
            from app.domain.knowledge.extractors import ExtractorRegistry
            ExtractorRegistry.initialize_defaults()
            logger.info("[Knowledge] ✓ Extractors initialized")
        except Exception as e:
            logger.warning(f"[Knowledge] Extractor initialization failed: {e}")

        # 2. FTS Search Index
        try:
            from app.domain.knowledge.services.search import get_fts_service
            fts = get_fts_service()
            await fts.initialize()
            logger.info("[Knowledge] ✓ FTS search index initialized")
        except Exception as e:
            logger.warning(f"[Knowledge] FTS initialization failed: {e}")

        # 3. Citation Tracker
        try:
            from app.domain.knowledge.services.citations import get_citation_tracker
            tracker = get_citation_tracker()
            await tracker.initialize()
            logger.info("[Knowledge] ✓ Citation tracker initialized")
        except Exception as e:
            logger.warning(f"[Knowledge] Citation tracker initialization failed: {e}")
