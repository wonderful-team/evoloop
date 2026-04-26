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
from typing import List

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


