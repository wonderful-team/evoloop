"""
Todo Rewind Handler
===================

Handles todo item cleanup when conversation is rewound.

This module provides event-driven todo cleanup for the rewind system,
deleting todo items that are linked to rolled-back messages.
"""

import logging

from sqlalchemy import delete, select

from app.core.rewind.events import RewindEventType
from app.core.events.base import AsyncEventBus
from app.core.events.decorators import event_register, event_subscribe
from app.core.rewind.events import RewindRequestedEvent, TodoCleanupEvent
from app.infrastructure.database.sql.database import session_scope

logger = logging.getLogger(__name__)


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
        from app.core.events.decorators import register_instance_handlers
        register_instance_handlers(instance, bus)
        return instance

    @event_subscribe(RewindEventType.REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event: RewindRequestedEvent) -> None:
        """
        Handle main rewind event - prepare todo cleanup.
        
        Extracts message IDs and publishes a TODO_CLEANUP event.
        """
        try:
            # Get message IDs to clean up
            message_ids = await self._find_message_ids(
                thread_id=event.thread_id,
                target_message_id=event.target_message_id,
                include_target=event.include_target
            )
            
            if message_ids:
                # Publish specific cleanup event
                from app.core.events import system_bus
                await system_bus.publish(TodoCleanupEvent(
                    thread_id=event.thread_id,
                    source_message_ids=message_ids
                ))
                logger.info(f"[TodoRewind] Prepared {len(message_ids)} messages for todo cleanup")
        except Exception as e:
            logger.error(f"[TodoRewind] Failed to prepare todo cleanup: {e}")

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
