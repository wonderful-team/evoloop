"""
Rewind Handlers
===============

Event handlers for conversation rewind operations.

This module provides event-driven cleanup handlers for the rewind system:
- MessageRewind: Deletes messages and their references
- (Other handlers are in their respective domain modules)

All handlers are auto-registered via @event_register decorator.
"""

import logging

from sqlalchemy import delete, select, update

from app.core.checkpoint.rewind.events import (
    MessagesCleanupEvent,
    RewindEventType,
    RewindRequestedEvent,
)
from app.core.checkpoint.rewind.exceptions import MessageNotFoundError, NoHumanMessageError
from app.core.events.base import AsyncEventBus
from app.core.events.decorators import event_register, event_subscribe
from app.infrastructure.database.sql.database import session_scope
from app.models import Message, MessageReference

logger = logging.getLogger(__name__)


@event_register()
class MessageRewind:
    """Event-driven message cleanup handler for rewind operations."""

    def __init__(self):
        self._deleted_count = 0

    @classmethod
    def register(cls, bus: AsyncEventBus) -> "MessageRewind":
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
        Handle main rewind event - determine message range and trigger cleanup.
        
        This is the primary entry point for message cleanup. It:
        1. Finds the target message (or last human message)
        2. Determines the range of messages to delete
        3. Publishes MESSAGES_CLEANUP event
        """
        try:
            # Find messages to delete
            message_ids = await self._find_messages_to_delete(
                thread_id=event.thread_id,
                target_message_id=event.target_message_id,
                include_target=event.include_target
            )
            
            if message_ids:
                # Publish specific cleanup event
                from app.core.events import system_bus
                await system_bus.publish(MessagesCleanupEvent(
                    thread_id=event.thread_id,
                    message_ids=message_ids,
                    delete_references=True
                ))
                logger.info(f"[MessageRewind] Prepared {len(message_ids)} messages for deletion")
            else:
                logger.info(f"[MessageRewind] No messages to delete for thread {event.thread_id}")
                
        except Exception as e:
            logger.error(f"[MessageRewind] Failed to prepare message cleanup: {e}")
            raise

    @event_subscribe(RewindEventType.MESSAGES_CLEANUP)
    async def _handle_messages_cleanup(self, event: MessagesCleanupEvent) -> None:
        """
        Handle specific message cleanup event.
        
        This performs the actual message and reference deletion.
        """
        try:
            count = await self._delete_messages(
                message_ids=event.message_ids,
                delete_references=event.delete_references
            )
            self._deleted_count = count
            logger.info(f"[MessageRewind] Deleted {count} messages and their references")
        except Exception as e:
            logger.error(f"[MessageRewind] Message cleanup failed: {e}")
            raise

    async def _find_messages_to_delete(
        self,
        thread_id: str,
        target_message_id: str | None,
        include_target: bool
    ) -> list[str]:
        """
        Find the range of messages to delete.
        
        Args:
            thread_id: The thread ID
            target_message_id: The message to rewind to (None = last human message)
            include_target: Whether to include the target message in deletion
            
        Returns:
            List of message IDs as strings
            
        Raises:
            MessageNotFoundError: If target message doesn't exist
            NoHumanMessageError: If no human message found and no target specified
        """
        async with session_scope() as session:
            min_id_to_delete = None
            
            if target_message_id:
                # Use specified target message
                try:
                    msg_id_int = int(target_message_id)
                    target_msg = await session.get(Message, msg_id_int)
                    
                    if not target_msg:
                        raise MessageNotFoundError(
                            f"Target message {target_message_id} not found",
                            thread_id=thread_id
                        )
                    
                    min_id_to_delete = target_msg.id
                    
                except (ValueError, TypeError):
                    logger.error(f"[MessageRewind] Invalid target message ID: {target_message_id}")
                    return []
            else:
                # Find last human message
                stmt = (
                    select(Message)
                    .where(Message.thread_id == thread_id)
                    .where(Message.role == "human")
                    .order_by(Message.id.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                last_human = result.scalar_one_or_none()
                
                if not last_human:
                    raise NoHumanMessageError(
                        "No human message found to rewind to",
                        thread_id=thread_id
                    )
                
                min_id_to_delete = last_human.id
            
            if min_id_to_delete is None:
                return []
            
            # Query all messages to delete
            if include_target:
                stmt = select(Message.id).where(
                    Message.thread_id == thread_id,
                    Message.id >= min_id_to_delete
                )
            else:
                stmt = select(Message.id).where(
                    Message.thread_id == thread_id,
                    Message.id > min_id_to_delete
                )
            
            result = await session.execute(stmt)
            return [str(row[0]) for row in result.all()]

    async def _delete_messages(
        self,
        message_ids: list[str],
        delete_references: bool = True
    ) -> int:
        """
        Delete messages and optionally their references.
        
        Args:
            message_ids: List of message IDs to delete
            delete_references: Whether to delete MessageReference records
            
        Returns:
            Number of messages deleted
        """
        if not message_ids:
            return 0
        
        # Convert string IDs to integers
        int_ids = [int(mid) for mid in message_ids if mid.isdigit()]
        
        if not int_ids:
            return 0
        
        async with session_scope() as session:
            # 1. Delete references first (if requested)
            if delete_references:
                ref_result = await session.execute(
                    delete(MessageReference)
                    .where(MessageReference.message_id.in_(int_ids))
                )
                logger.debug(f"[MessageRewind] Deleted {ref_result.rowcount} references")
            
            # 2. Update parent_id for messages pointing to deleted messages
            # This prevents foreign key constraint issues
            await session.execute(
                update(Message)
                .where(Message.parent_id.in_(int_ids))
                .values(parent_id=None)
            )
            
            # 3. Delete messages
            msg_result = await session.execute(
                delete(Message).where(Message.id.in_(int_ids))
            )
            
            deleted_count = msg_result.rowcount
            logger.info(f"🗑️ Deleted {deleted_count} Message records")
            return deleted_count

    async def cleanup(self, message_ids: list[str], **kwargs) -> int:
        """Direct cleanup entry point (non-event-driven usage)."""
        delete_references = kwargs.get("delete_references", True)
        return await self._delete_messages(message_ids, delete_references)

    def get_deleted_count(self) -> int:
        """Get the count of messages deleted in the last operation."""
        return self._deleted_count
