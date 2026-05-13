"""
Knowledge Event Subscribers
===========================

Event subscribers for knowledge initialization and harvesting.
"""

import asyncio
import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.schemas import SessionCompletedEvent
from app.infrastructure.config.service import SystemConfigService
from app.core.llm import InternalLLMService
from app.domain.knowledge.schemas import KnowledgeHarvestingResult
from app.domain.knowledge.models import MarkdownDocument, DocumentMetadata
from app.utils import render_template

logger = logging.getLogger(__name__)


@event_register()
class KnowledgeInitSubscriber:
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
class KnowledgeHarvestingSubscriber:
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
            # Trigger background harvesting process
            asyncio.create_task(self._process_harvesting(data))
        finally:
            ContextManager.reset(token)

    async def _process_harvesting(self, data):
        """Background process for deep knowledge extraction and ingestion."""
        thread_id = data.thread_id
        project_id = data.project_id
        model = data.model

        # 1. Check feature flags / settings
        auto_extract = SystemConfigService.get_value("AUTO_KNOWLEDGE_EXTRACTION", "true").lower() == "true"
        if not auto_extract:
            logger.debug(f"[Knowledge] Auto-extraction disabled for thread {thread_id}")
            return

        logger.info(f"[Knowledge] 🧠 Harvesting knowledge from thread {thread_id}...")

        try:
            # 2. Prepare context and history
            from app.core.engine.message.repository import MessageRepository
            repo = MessageRepository(thread_id=thread_id, project_id=project_id)
            db_messages, _, _ = await repo.get_full_history()
            
            if not db_messages:
                logger.debug(f"[Knowledge] No messages found for thread {thread_id}, skipping")
                return

            user_lang = SystemConfigService.get_language_preference()
            
            # 3. Render prompt
            prompt_text = render_template(
                "core/knowledge/extraction.prompt.j2",
                thread_id=thread_id,
                project_id=project_id,
                user_language=user_lang,
                messages=[{"role": m.role, "content": m.content} for m in db_messages],
                summary_needed=True
            )

            # 4. Call InternalLLMService
            model_name = SystemConfigService.get_value("LLM_MODEL")
            result = await InternalLLMService.invoke_structured(
                messages=[{"role": "system", "content": prompt_text}],
                purpose="knowledge_extraction",
                output_schema=KnowledgeHarvestingResult,
                temperature=0.0,
                model_name=model_name
            )

            if not result.items:
                logger.info(f"[Knowledge] No valuable knowledge identified for thread {thread_id}")
                return

            # 5. Persist valid extractions
            from app.domain.knowledge.services.store import get_store_service
            store = get_store_service()
            
            count = 0
            for item in result.items:
                if item.confidence < 0.7:
                    continue
                
                # Create domain objects
                doc = MarkdownDocument(
                    source=f"harvest:{thread_id}",
                    content=item.content,
                    mime_type="text/markdown",
                    metadata={"title": item.title}
                )
                
                meta = DocumentMetadata(
                    source_file=f"harvest:{thread_id}",
                    source_mime_type="text/markdown",
                    file_size_bytes=len(item.content),
                    title=item.title,
                    summary=result.summary,
                    keywords=item.tags
                )
                
                # Path construction: harvests/{category}/{title}
                safe_title = "".join([c if c.isalnum() else "_" for c in item.title]).lower()
                kb_path = f"{item.category}/{safe_title}"
                
                store.save_document(
                    document=doc,
                    metadata=meta,
                    collection="harvests",
                    path=kb_path,
                    source_project_id=project_id
                )
                count += 1
            
            logger.info(f"[Knowledge] ✅ Successfully harvested {count} knowledge items for thread {thread_id}")

        except Exception as e:
            logger.error(f"[Knowledge] Harvesting failed for thread {thread_id}: {e}")
