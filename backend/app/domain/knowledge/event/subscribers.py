"""
Knowledge Event Subscribers
===========================

Event subscribers for knowledge initialization and harvesting.
"""

import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.schemas import SessionCompletedEvent

logger = logging.getLogger(__name__)


@event_register()
class KnowledgeInitHandler:
    """
    Handles knowledge-related system events on application startup.

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


@event_register()
class KnowledgeHarvestingHandler:
    """
    Handles automatic Knowledge harvesting from session history.
    """

    @event_subscribe(SystemEventType.SESSION_COMPLETED)
    async def on_session_completed(self, event: SessionCompletedEvent):
        """
        Triggered when a session finishes successfully.
        Extracts documentation and architectural decisions.
        """
        data = event.data
        logger.info(f"[Knowledge] 📚 Session completed for {data.thread_id}. Auditing for knowledge artifacts...")

        # Initialize background context for auditing
        from app.core.context.manager import ContextManager, EvoContext
        ctx = EvoContext(
            thread_id=data.thread_id,
            project_id=data.project_id,
            active_model=data.model
        )
        token = ContextManager.set(ctx)

        try:
            # TODO: Implement harvesting logic
            pass
        finally:
            ContextManager.reset(token)

    async def _process_harvesting(self, data):
        """Background process for deep knowledge extraction and ingestion."""
        # TODO: Real implementation utilizing InternalLLMService and KnowledgeStoreService
        pass
