"""
Todo Module Event Subscribers
=============================

Handles todo lifecycle (harvesting), memory context provision, and rewind cleanup.
"""

import logging
from typing import List

from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.core.engine.rewind.event import RewindEventType, RewindRequestedEvent
from app.core.events import SystemEventType
from app.core.events.base import AsyncEventBus
from app.core.events.decorators import event_register, event_subscribe, register_instance_handlers
from app.core.events.schemas import SessionCompletedEvent
from app.core.memory.event import (
    MEMORY_CONTEXT_GATHER_EVENT_TYPE,
    MemoryContextGatherEvent,
)
from app.domain.todo.event.schemas import TodoCleanupEvent
from app.infrastructure.database.sql.database import session_scope
from app.utils import render_template

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


@event_register()
class TodoMemoryContextProvider:
    """
    Provides pending todo context for memory extraction.

    Automatically registered via @event_register and discovered at startup.
    Renders its own markdown fragment via Jinja2 template — memory layer
    only sees the final formatted string.
    """

    @event_subscribe(MEMORY_CONTEXT_GATHER_EVENT_TYPE)
    async def on_context_gather(self, event: MemoryContextGatherEvent) -> None:
        """Render todo context fragment and append to event data."""
        project_id = event.data.project_id
        if not project_id:
            return

        try:
            from app.domain.todo.service import TodoService
            from app.infrastructure.database.sql.database import session_scope

            async with session_scope() as session:
                todo_service = TodoService(session)
                todos = await todo_service.list_pending_by_project(project_id)
                if todos:
                    fragment = render_template(
                        "domain/todo/memory_context.j2",
                        todos=[
                            {"title": t.title, "priority": t.priority}
                            for t in todos[:20]
                        ],
                    )
                    if fragment.strip():
                        event.data.context_fragments.append(fragment.strip())
        except Exception as e:
            logger.warning(f"[TodoContextProvider] Failed to render TODO context: {e}")


@event_register()
class TodoRewind:
    """Event-driven todo cleanup handler for rewind operations."""

    def __init__(self):
        self._deleted_count = 0

    @classmethod
    def register(cls, bus: AsyncEventBus) -> "TodoRewind":
        """
        Register this handler to the event bus.
        
        Args:
            bus: The event bus to subscribe to
            
        Returns:
            The handler instance
        """
        instance = cls()
        register_instance_handlers(instance, bus)
        return instance

    @event_subscribe(RewindEventType.REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event: RewindRequestedEvent) -> None:
        """
        Handle main rewind event - prepare todo cleanup.
        
        Uses event.affected_message_ids (pre-computed by RewindOrchestrator)
        to avoid race conditions with other handlers querying the messages table.
        """
        message_ids = event.affected_db_message_ids or event.affected_message_ids or await self._find_message_ids(
            thread_id=event.thread_id,
            target_message_id=event.target_message_id,
            include_target=event.include_target
        )
        
        if message_ids:
            count = await self._delete_todos(message_ids)
            self._deleted_count = count
            event.results["todos"] = count

            from app.domain.todo.event.publishers import publish_todo_cleanup
            await publish_todo_cleanup(
                thread_id=event.thread_id,
                source_message_ids=message_ids,
            )
            logger.info(f"[TodoRewind] Deleted {count} todo items for thread {event.thread_id}")
        else:
            logger.debug(f"[TodoRewind] No todo items found to delete for thread {event.thread_id}")

    @event_subscribe(RewindEventType.TODO_CLEANUP)
    async def _handle_todo_cleanup(self, event: TodoCleanupEvent) -> None:
        """
        Handle specific todo cleanup event.
        
        This performs the actual todo deletion.
        """
        try:
            count = await self._delete_todos(event.source_message_ids)
            self._deleted_count = count
            logger.info(f"[TodoRewind] Deleted {count} todo items")
        except Exception as e:
            logger.error(f"[TodoRewind] Todo cleanup failed: {e}")
            raise

    async def _find_message_ids(
        self,
        thread_id: str,
        target_message_id: str | None,
        include_target: bool
    ) -> list[str]:
        """
        Find message IDs to clean up for the given thread.
        
        Args:
            thread_id: The thread ID
            target_message_id: The message to rewind to
            include_target: Whether to include the target message
            
        Returns:
            List of message IDs as strings
        """
        from app.models import Message
        
        async with session_scope() as session:
            stmt = select(Message.id).where(Message.thread_id == thread_id)
            
            if target_message_id:
                target_id = int(target_message_id)
                if include_target:
                    stmt = stmt.where(Message.id >= target_id)
                else:
                    stmt = stmt.where(Message.id > target_id)

            result = await session.execute(stmt)
            return [str(row[0]) for row in result.all()]

    async def _delete_todos(self, source_message_ids: list[str]) -> int:
        """
        Delete todo items linked to the given message IDs.
        
        Args:
            source_message_ids: List of source message IDs
            
        Returns:
            Number of todos deleted
        """
        from app.models.todo import TodoItem
        
        if not source_message_ids:
            return 0
        
        async with session_scope() as session:
            # Convert string IDs to integers
            int_ids = [int(mid) for mid in source_message_ids if mid.isdigit()]
            
            if not int_ids:
                return 0
            
            stmt = delete(TodoItem).where(TodoItem.source_message_id.in_(int_ids))
            result = await session.execute(stmt)
            
            deleted_count = result.rowcount
            logger.info(f"🗑️ Deleted {deleted_count} TodoItem records")
            return deleted_count

    async def cleanup(self, message_ids: list[str], **kwargs) -> int:
        """Direct cleanup entry point (non-event-driven usage)."""
        return await self._delete_todos(message_ids)

    def get_deleted_count(self) -> int:
        """Get the count of todos deleted in the last operation."""
        return self._deleted_count
