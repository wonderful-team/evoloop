"""
Todo Module Lifecycle Handlers
==============================

This module handles the automatic "Harvesting" of todo items at the end of a session.
It subscribes to SystemEventType.SESSION_COMPLETED to analyze conversation history.

Implementation Strategy:
1. Listen for SESSION_COMPLETED events.
2. Use InternalLLMService to run a background "Extraction Agent".
3. The Agent uses a specialized prompt to identify:
    - Task commitments made by the AI or User.
    - Blocking items requiring human/third-party intervention.
    - "Next Steps" explicitly discussed but not yet executed.
4. Extracted items are validated and persisted via TodoService.
"""

import logging
from typing import List

from pydantic import BaseModel, Field

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.schema import SessionCompletedEvent

logger = logging.getLogger(__name__)


class ExtractedTodo(BaseModel):
    """Schema for a single extracted todo item."""
    title: str = Field(..., description="Short, actionable title")
    description: str = Field(..., description="Detailed context of the task")
    priority: str = Field("medium", description="low|medium|high")
    category: str = Field("general", description="coordination|task|feature|bug")
    reasoning: str = Field(..., description="Why this item was extracted from the history")


class TodoHarvestingResult(BaseModel):
    """Container for multiple extracted todos."""
    todos: List[ExtractedTodo] = Field(default_factory=list)


@event_register()
class TodoLifecycleHandler:
    """
    Handles automatic Todo extraction from session history.
    """

    @event_subscribe(SystemEventType.SESSION_COMPLETED)
    async def on_session_completed(self, event: SessionCompletedEvent):
        """
        Triggered when a session finishes successfully.
        Extracts future tasks and coordination items.
        """
        data = event.data
        logger.info(f"[Todo] 📝 Session completed for {data.thread_id}. Checking for pending actions...")

        # Initialize background context for extraction
        from app.core.context.manager import ContextManager, EvoContext
        ctx = EvoContext(
            thread_id=data.thread_id,
            project_id=data.project_id,
            active_model=data.model
        )
        token = ContextManager.set(ctx)

        try:
            # TODO: Implement harvesting logic
            # 1. Check feature flags / settings for auto-todo-extraction
            # 2. Prepare the harvesting prompt using 'core/todo/extraction.prompt.j2'
            # 3. Call InternalLLMService.invoke_structured with TodoHarvestingResult schema
            # 4. Filter results based on confidence/relevance
            # 5. Iteratively call TodoService.create for each valid extraction
            
            # NOTE: This should run in a background task to avoid blocking the engine
            # asyncio.create_task(self._harvest_todos(data))
            pass
        finally:
            ContextManager.reset(token)

    async def _harvest_todos(self, data):
        """Internal background method for deep analysis and storage."""
        # TODO: Real implementation involving LLM and TodoService
        pass
