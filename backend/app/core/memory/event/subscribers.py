"""
Memory Module Event Subscribers
================================

Handles application-level shutdown, session completion, and rewind cleanup
for the memory domain.
"""
import asyncio
import logging

from app.core.engine.rewind.event import RewindEventType, RewindRequestedEvent
from app.core.events import SystemEventType
from app.core.events.base import AsyncEventBus
from app.core.events.decorators import event_register, event_subscribe, register_instance_handlers
from app.core.events.schema import SessionCompletedEvent
from app.core.memory.event.schemas import MemoryCleanupEvent

logger = logging.getLogger(__name__)


@event_register()
class MemoryLifecycleHandler:
    """
    Handles application-level lifecycle events for the Memory domain.
    
    Includes:
    - Auto-extraction of conversation history on session completion
    - Graceful shutdown of memory container on app stop
    """

    @event_subscribe(SystemEventType.SESSION_COMPLETED)
    async def on_session_completed(self, event: SessionCompletedEvent):
        """
        Trigger automatic memory extraction.
        """
        data = event.data
        logger.info(f"[Memory] 🧠 Session completed for thread {data.thread_id}. Triggering auto-extraction...")

        try:
            from app.core.context.manager import ContextManager, EvoContext
            from app.core.memory.auto_extraction import trigger_auto_extraction

            # Create a dedicated context for the background extraction task
            ctx = EvoContext(
                thread_id=data.thread_id,
                project_id=data.project_id,
                user_id=data.user_id,
                active_model=data.model
            )

            async def _run_extraction_background():
                # Set context for this specific coroutine
                token = ContextManager.set(ctx)
                try:
                    await trigger_auto_extraction(
                        thread_id=data.thread_id,
                        messages=data.messages,
                        project_id=data.project_id,
                        user_id=data.user_id
                    )
                finally:
                    ContextManager.reset(token)

            # Fire and forget auto-extraction in a background task
            asyncio.create_task(_run_extraction_background())
            logger.debug(f"[Memory] ✓ Auto-extraction background task started for {data.thread_id}")
        except Exception as e:
            logger.error(f"[Memory] Failed to trigger auto-extraction: {e}")

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        """Handle APP_STOPPING event - shutdown memory container."""
        try:
            from app.core.memory.lifespan import MemoryLifespanManager
            await MemoryLifespanManager.shutdown()
            logger.info("[Memory] Memory container shutdown")
        except Exception as e:
            logger.warning(f"[Memory] Failed to shutdown memory container: {e}")


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
            # Prefer pre-computed affected_message_ids to avoid execution-order
            # dependency with MessageRewind (which may have already deleted rows).
            message_ids = event.affected_message_ids or await self._find_message_ids(
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
                from app.core.memory.event.publishers import publish_memory_cleanup
                await publish_memory_cleanup(
                    thread_id=event.thread_id,
                    source_message_ids=message_ids,
                )
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
