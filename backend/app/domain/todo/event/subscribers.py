"""
Todo Module Event Subscribers
=============================

Handles todo lifecycle (harvesting), memory context provision, and rewind cleanup.
"""

import logging

from sqlalchemy import delete, or_, select

from app.core.engine.event import (
    ExtractionCompletedEvent,
    ExtractionRequest,
    ExtractionRequestedEvent,
)
from app.core.engine.rewind import REWIND_REQUESTED, RewindRequestedEvent
from app.core.events import SystemEventType
from app.core.events.decorators import (
    event_register,
    event_subscribe,
)
from app.domain.todo.schemas import TodoCreate
from app.domain.todo.service import TodoService
from app.infrastructure.database import session_scope

logger = logging.getLogger(__name__)


@event_register()
class TodoLifecycleSubscriber:
    """
    Handles automatic Todo extraction from session history.
    """

    @event_subscribe(SystemEventType.EXTRACTION_REQUESTED)
    async def on_extraction_requested(self, event: ExtractionRequestedEvent):
        """Register the todo extraction schema to the event."""
        event.requests.append(
            ExtractionRequest(
                name="todo",
                description=(
                    "Extract action items, pending tasks, follow-ups, and coordination "
                    "needs that should be tracked from the conversation."
                ),
                schema_dict={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Short title of the task",
                        },
                        "description": {
                            "type": "string",
                            "description": "Detailed description of what needs to be done",
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "Priority level",
                        },
                        "category": {"type": "string", "description": "Task category"},
                        "confidence": {
                            "type": "number",
                            "description": "Confidence score 0-1",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Why this task is necessary",
                        },
                    },
                    "required": ["title", "description", "priority"],
                },
            )
        )

    @event_subscribe(SystemEventType.EXTRACTION_COMPLETED)
    async def on_extraction_completed(self, event: ExtractionCompletedEvent):
        """
        Triggered when background extraction finishes.
        Extracts future tasks and coordination items.
        """
        extracted_data = event.extracted_data or {}
        items = extracted_data.get("todo")
        if not items:
            return

        from app.domain.todo.schemas import ExtractedTodo

        todo_items = []
        for item in items:
            todo_items.append(
                ExtractedTodo(
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    priority=item.get("priority", "medium"),
                    category=item.get("category", "general"),
                    confidence=item.get("confidence", 0.7),
                    reasoning=item.get("reasoning"),
                )
            )

        count = await persist_todo_extractions(
            todo_items, event.thread_id, event.project_id
        )
        if count:
            logger.info(f"[Todo] ✅ Persisted {count} todos from audit extraction")


async def persist_todo_extractions(
    todos: list, thread_id: str, project_id: int | None
) -> int:
    """Persist extracted todo items (no LLM calls)."""
    async with session_scope() as session:
        service = TodoService(session)
        count = 0
        for ext in todos:
            if ext.confidence < 0.7:
                continue
            await service.create(
                TodoCreate(
                    title=ext.title,
                    description=ext.description,
                    priority=ext.priority,
                    category=ext.category,
                    project_id=project_id,
                ),
                source_conversation_id=thread_id,
            )
            count += 1
    return count


@event_register()
class TodoRewind:
    """Event-driven todo cleanup handler for rewind operations."""

    def __init__(self):
        self._deleted_count = 0

    @event_subscribe(REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event: RewindRequestedEvent) -> None:
        """Handle main rewind event - delete todo items."""
        message_ids = event.affected_message_ids or await self._find_message_ids(
            thread_id=event.thread_id,
            target_message_id=event.target_message_id,
            include_target=event.include_target,
        )

        if message_ids or event.affected_run_ids:
            count = await self._delete_todos(
                message_ids=message_ids, run_ids=event.affected_run_ids
            )
            self._deleted_count = count
            event.results["todos"] = count
            logger.info(
                f"[TodoRewind] Deleted {count} todo items for thread {event.thread_id}"
            )
        else:
            logger.debug(
                f"[TodoRewind] No todo items found to delete for thread {event.thread_id}"
            )

    async def _find_message_ids(
        self, thread_id: str, target_message_id: str | None, include_target: bool
    ) -> list[str]:
        """Find message IDs to clean up for the given thread."""
        from app.models import Message

        async with session_scope() as session:
            stmt = select(Message.id).where(Message.thread_id == thread_id)

            if target_message_id:
                # Resolve sequence from UUID
                stmt_target = select(Message.sequence_number).where(
                    Message.id == target_message_id
                )
                res_target = await session.execute(stmt_target)
                target_seq = res_target.scalar_one_or_none()

                if target_seq is None:
                    logger.warning(
                        f"[TodoRewind] Target message {target_message_id} not found"
                    )
                    return []

                if include_target:
                    stmt = stmt.where(Message.sequence_number >= target_seq)
                else:
                    stmt = stmt.where(Message.sequence_number > target_seq)

            result = await session.execute(stmt)
            return [str(row[0]) for row in result.all()]

    async def _delete_todos(
        self, message_ids: list[str], run_ids: list[str] | None = None
    ) -> int:
        """
        Delete todo items by message IDs or run IDs.
        """
        from app.models.todo import TodoItem

        if not message_ids and not run_ids:
            return 0

        async with session_scope() as session:
            stmt = delete(TodoItem)

            conditions = []
            if message_ids:
                conditions.append(TodoItem.source_message_id.in_(message_ids))
            if run_ids:
                conditions.append(TodoItem.run_id.in_(run_ids))

            if len(conditions) > 1:
                stmt = stmt.where(or_(*conditions))
            else:
                stmt = stmt.where(conditions[0])

            result = await session.execute(stmt)
            count = result.rowcount
            logger.info(f"[TodoRewind] Deleted {count} todo items")
            return count

    async def cleanup(self, message_ids: list[str], **kwargs) -> int:
        """Direct cleanup entry point (non-event-driven usage)."""
        return await self._delete_todos(message_ids=message_ids)

    def get_deleted_count(self) -> int:
        """Get the count of todos deleted in the last operation."""
        return self._deleted_count
