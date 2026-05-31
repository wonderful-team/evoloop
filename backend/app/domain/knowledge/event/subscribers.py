"""
Knowledge Event Subscribers
===========================

Event subscribers for knowledge initialization and harvesting.
"""

import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.schemas.lifecycle import ExtractionRequestedEvent, ExtractionCompletedEvent, ExtractionRequest
from app.domain.knowledge.models import DocumentMetadata, MarkdownDocument

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

    @event_subscribe(SystemEventType.EXTRACTION_REQUESTED)
    async def on_extraction_requested(self, event: ExtractionRequestedEvent):
        """Register the knowledge extraction schema to the event."""
        event.requests.append(
            ExtractionRequest(
                name="knowledge",
                description=(
                    "Extract architectural decisions, design patterns, business rules, "
                    "environment configuration, and reusable technical references from "
                    "the conversation."
                ),
                schema_dict={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Short descriptive title of the knowledge",
                        },
                        "content": {
                            "type": "string",
                            "description": "The actual knowledge content in Markdown",
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "technical_rule",
                                "business_logic",
                                "workflow",
                                "architecture",
                                "environment",
                            ],
                            "description": "Category of the knowledge",
                        },
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "source_context": {
                            "type": "string",
                            "description": "Excerpt from conversation for tracing",
                        },
                    },
                    "required": ["title", "content", "category"],
                }
            )
        )

    @event_subscribe(SystemEventType.EXTRACTION_COMPLETED)
    async def on_extraction_completed(self, event: ExtractionCompletedEvent):
        """
        Triggered when background extraction finishes.
        Extracts documentation and architectural decisions.
        """
        extracted_data = getattr(event, "extracted_data", {}) or {}
        items = extracted_data.get("knowledge")
        if not items:
            return

        from app.domain.knowledge.schemas import ExtractedKnowledge

        knowledge_items = []
        for item in items:
            knowledge_items.append(
                ExtractedKnowledge(
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    category=item.get("category", "technical_rule"),
                    tags=item.get("tags", []),
                    confidence=item.get("confidence", 0.7),
                    source_context=item.get("source_context"),
                )
            )

        count = await persist_knowledge_extractions(
            knowledge_items, "", event.thread_id, event.project_id
        )
        if count:
            logger.info(f"[Knowledge] ✅ Automatically harvested and indexed {count} items from session")


async def persist_knowledge_extractions(
    items: list,
    summary: str,
    thread_id: str,
    project_id: int | None,
) -> int:
    """Persist extracted knowledge items (no LLM calls)."""
    from app.domain.knowledge.services.store import get_store_service

    store = get_store_service()

    count = 0
    for item in items:
        if item.confidence < 0.7:
            continue

        doc = MarkdownDocument(
            source=f"harvest:{thread_id}",
            content=item.content,
            mime_type="text/markdown",
            metadata={"title": item.title},
        )

        meta = DocumentMetadata(
            source_file=f"harvest:{thread_id}",
            source_mime_type="text/markdown",
            file_size_bytes=len(item.content),
            title=item.title,
            summary=summary,
            keywords=item.tags,
        )

        safe_title = "".join([c if c.isalnum() else "_" for c in item.title]).lower()
        kb_path = f"{item.category}/{safe_title}"

        store.save_document(
            document=doc,
            metadata=meta,
            collection="harvests",
            path=kb_path,
            source_project_id=project_id,
        )
        count += 1

    return count
