"""
Memory Rewind Handler
=====================

Handles memory cleanup when conversation is rewound.

This module provides event-driven memory cleanup for the rewind system,
deleting memories that are linked to rolled-back messages.
"""

import logging

from pydantic import Field

from app.core.engine.rewind.events import RewindEvent, RewindEventType, RewindRequestedEvent
from app.core.events.base import AsyncEventBus
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)



class MemoryCleanupEvent(RewindEvent):
    """Published to trigger memory deletion."""
    source_message_ids: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        self.event_type = RewindEventType.MEMORY_CLEANUP
        self.data = {
            "thread_id": self.thread_id,
            "source_message_ids": self.source_message_ids,
            "run_ids": self.run_ids,
        }

@event_register()
class MemoryRewind:
    """Event-driven memory cleanup handler for rewind operations."""

    def __init__(self):
        self._deleted_count = 0

    @classmethod
    def register(cls, bus: AsyncEventBus) -> "MemoryRewind":
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
        Handle main rewind event - prepare memory cleanup.
        
        This extracts message IDs and run IDs from the rewind request
        and publishes a MEMORY_CLEANUP event.
        """
        try:
            # Get message IDs to clean up
            message_ids = await self._find_message_ids(
                thread_id=event.thread_id,
                target_message_id=event.target_message_id,
                include_target=event.include_target
            )

            if message_ids:
                # Perform deletion directly to capture count for aggregation
                count = await self._delete_memories(
                    source_message_ids=message_ids,
                    run_ids=[]
                )
                self._deleted_count = count

                # Report back to the main event
                event.results["memories"] = count

                # Still publish specific cleanup event for other potential listeners
                from app.core.events import system_bus
                await system_bus.publish(MemoryCleanupEvent(
                    thread_id=event.thread_id,
                    source_message_ids=message_ids,
                    run_ids=[]
                ))
                logger.info(f"[MemoryRewind] Deleted {count} memories for thread {event.thread_id}")
            else:
                logger.debug(f"[MemoryRewind] No memories found to delete for thread {event.thread_id}")

        except Exception as e:
            error_msg = f"Memory cleanup failed: {e}"
            logger.error(f"[MemoryRewind] {error_msg}")
            event.errors.append(error_msg)
            event.success = False

    @event_subscribe(RewindEventType.MEMORY_CLEANUP)
    async def _handle_memory_cleanup(self, event: MemoryCleanupEvent) -> None:
        """
        Handle specific memory cleanup event.
        
        This performs the actual memory deletion.
        """
        try:
            count = await self._delete_memories(
                source_message_ids=event.source_message_ids,
                run_ids=event.run_ids
            )
            self._deleted_count = count
            logger.info(f"[MemoryRewind] Deleted {count} memories")
        except Exception as e:
            logger.error(f"[MemoryRewind] Memory cleanup failed: {e}")
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
        from sqlalchemy import select

        from app.infrastructure.database.sql.database import session_scope
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
            # Convert to strings for consistency
            return [str(row[0]) for row in result.all()]

    async def _delete_memories(
        self,
        source_message_ids: list[str],
        run_ids: list[str]
    ) -> int:
        """
        Delete memories linked to the given message IDs and run IDs.
        
        Args:
            source_message_ids: List of source message IDs
            run_ids: List of run IDs
            
        Returns:
            Number of memories deleted
        """
        from app.core.memory.lifespan import MemoryLifespanManager

        count = 0

        try:
            # Initialize memory manager if needed
            if not MemoryLifespanManager.is_initialized():
                await MemoryLifespanManager.ainitialize()

            container = MemoryLifespanManager.get_container()
            memory_manager = container.memory_manager

            # Delete by source message ID
            for msg_id in source_message_ids:
                try:
                    # Use structured filters for precise metadata matching
                    results = await memory_manager.search_memories(
                        query="",
                        filters={"source_message_id": msg_id},
                        limit=100
                    )

                    for mem in results:
                        if await memory_manager.delete_memory(mem.id):
                            count += 1

                except Exception as e:
                    logger.warning(f"[MemoryRewind] Failed to delete memories for msg {msg_id}: {e}")

            # TODO: Delete by run_id if memory system supports it
            # This would require the memory system to index by run_id

        except Exception as e:
            logger.error(f"[MemoryRewind] Memory manager initialization failed: {e}")

        return count

    async def cleanup(self, message_ids: list[str], **kwargs) -> int:
        """Direct cleanup entry point (non-event-driven usage)."""
        run_ids = kwargs.get("run_ids", [])
        return await self._delete_memories(
            source_message_ids=message_ids,
            run_ids=run_ids
        )

    def get_deleted_count(self) -> int:
        """Get the count of memories deleted in the last operation."""
        return self._deleted_count
