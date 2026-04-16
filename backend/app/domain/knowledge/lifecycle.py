"""
Knowledge Module Lifecycle Handlers
==================================

This module handles the automatic "Harvesting" of knowledge documents at the end of a session.
It subscribes to SystemEventType.SESSION_COMPLETED to analyze if any valuable technical
knowledge or documentation was generated during the session.

Implementation Strategy:
1. Listen for SESSION_COMPLETED events.
2. Use InternalLLMService to "Audit" the conversation history.
3. The Audit Logic focuses on:
    - Identifying "Document-like" outputs (Design docs, API Specs, Guides, Decision Logs).
    - Judging "Long-term Value": Is this useful beyond the current task context?
    - Detecting "New Insights": Did the agent or user uncover new rules or project facts?
4. If a document is identified as "Worthy":
    - Convert it into a standard MarkdownDocument.
    - Save it into the KnowledgeStore under a relevant collection (e.g., 'auto-harvested' or 'project-docs').
    - Index the document for future retrieval.
"""

import logging
import asyncio
from typing import List, Optional
from pydantic import BaseModel, Field

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.schema import SessionCompletedEvent

logger = logging.getLogger(__name__)


class KnowledgeCandidate(BaseModel):
    """Schema for a potential knowledge document."""
    title: str = Field(..., description="A clear, searchable title for the knowledge entry")
    content: str = Field(..., description="The actual markdown content to be saved")
    category: str = Field("doc", description="doc|guide|spec|decision|rule")
    tags: List[str] = Field(default_factory=list)
    reason_for_harvesting: str = Field(..., description="Why LLM thinks this is worth saving for the long-term")
    confidence: float = Field(..., description="0.0 to 1.0 confidence in the value of this knowledge")


class KnowledgeHarvestingResult(BaseModel):
    """Container for multiple discovered knowledge items."""
    candidates: List[KnowledgeCandidate] = Field(default_factory=list)


@event_register()
class KnowledgeLifecycleHandler:
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

        # TODO: Implement harvesting logic
        # 1. Check if history contains meaningful generated content (e.g., more than 500 chars change)
        # 2. Prepare analysis prompt using 'core/knowledge/extraction.prompt.j2'
        # 3. Call InternalLLMService.invoke_structured with KnowledgeHarvestingResult
        # 4. For each high-confidence candidate:
        #    a. Create a MarkdownDocument with appropriate metadata
        #    b. Call KnowledgeStoreService.save_document
        
        # NOTE: This runs in background to prevent stalling the engine response
        # asyncio.create_task(self._process_harvesting(data))
        pass

    async def _process_harvesting(self, data):
        """Background process for deep knowledge extraction and ingestion."""
        # TODO: Real implementation utilizing InternalLLMService and KnowledgeStoreService
        pass
