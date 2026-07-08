"""
Memory Module Event Subscribers
================================

Handles application-level shutdown, session completion, and rewind cleanup
for the memory domain.
"""
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.engine.event.schemas import ConversationDeletedEvent
from app.core.engine.event.types import ConversationEventType
from app.core.engine.rewind import REWIND_REQUESTED, RewindRequestedEvent
from app.core.events import SystemEventType
from app.core.events.base import AsyncEventBus
from app.core.events.decorators import (
    event_register,
    event_subscribe,
    register_instance_handlers,
)
from app.core.events.schemas.lifecycle import (
    ExtractionCompletedEvent,
    ExtractionRequest,
    ExtractionRequestedEvent,
)
from app.infrastructure.database import session_scope
from app.models import Message

logger = logging.getLogger(__name__)


@event_register()
class MemoryLifecycleSubscriber:
    """
    Handles application-level lifecycle events for the Memory domain.
    """

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        """Handle APP_STOPPING event - shutdown memory container."""
        try:
            from app.core.memory.lifespan import MemoryLifespanManager
            await MemoryLifespanManager.shutdown()
            logger.info("[Memory] Memory container shutdown")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[Memory] Failed to shutdown memory container: {e}")

    @event_subscribe(SystemEventType.EXTRACTION_REQUESTED)
    async def on_extraction_requested(self, event: ExtractionRequestedEvent):
        """Register the memory extraction schema to the event."""
        event.requests.append(
            ExtractionRequest(
                name="memory",
                description=(
                    "Extract user preferences, personal facts, project-specific concepts, "
                    "contextual information about the user's workflow, and important decisions "
                    "that should be remembered across sessions."
                ),
                schema_dict={
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": [
                                "user",
                                "feedback",
                                "project",
                                "reference",
                                "concept",
                                "episode",
                            ],
                            "description": "Memory type classification",
                        },
                        "content": {
                            "type": "string",
                            "description": "The actual memory content",
                        },
                        "title": {
                            "type": "string",
                            "description": "A short, descriptive title",
                        },
                        "description": {
                            "type": "string",
                            "description": "A brief explanation of why this memory is relevant",
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Confidence score from 0.0 to 1.0",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of relevant tags",
                        },
                        "source_file_path": {
                            "type": "string",
                            "description": "The workspace-relative file path related to this memory/gotcha, if any (e.g. 'app/main.py')",
                        },
                    },
                    "required": ["type", "content", "title", "confidence"],
                }
            )
        )

    @event_subscribe(SystemEventType.EXTRACTION_COMPLETED)
    async def on_extraction_completed(self, event: ExtractionCompletedEvent):
        extracted_data = event.extracted_data or {}
        items = extracted_data.get("memory")
        if not items:
            return

        from app.core.memory.lifespan import MemoryLifespanManager
        from app.core.memory.models import MemoryEntry, MemoryType

        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        memory_manager = container.memory_manager

        count = 0
        for item in items:
            entry = MemoryEntry(
                type=MemoryType(item.get("type", "project")),
                title=item.get("title", item.get("content", "")[:60]),
                content=item.get("content", ""),
                description=item.get("description", ""),
                tags=item.get("tags", []),
                project_id=event.project_id,
                member_id=event.member_id,
                source="harvest:finish",
                run_id=event.run_id,
                confidence=item.get("confidence", 0.7),
                source_thread_id=event.thread_id,
                source_run_id=event.run_id,
                source_file_path=item.get("source_file_path"),
            )
            await memory_manager.save_memory(entry)
            count += 1

        if count:
            logger.info(f"[Memory] ✅ Persisted {count} memories from audit extraction")


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

    @event_subscribe(REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event: RewindRequestedEvent) -> None:
        """
        Handle main rewind event - prepare memory cleanup.
        """
        logger.info(f"[MemoryRewind] 🔄 Rewind requested for thread {event.thread_id}, affected msgs: {len(event.affected_message_ids)}")
        try:
            # Get message IDs to clean up
            # Prefer pre-computed affected_message_ids to avoid execution-order
            # dependency with MessageRewind (which may have already deleted rows).
            message_ids = event.affected_message_ids or await self._find_message_ids(
                thread_id=event.thread_id,
                target_message_id=event.target_message_id,
                include_target=event.include_target
            )

            if message_ids or event.affected_run_ids:
                logger.info(f"[MemoryRewind] Identified {len(message_ids)} affected messages and {len(event.affected_run_ids)} run_ids for thread {event.thread_id}")

                # Perform deletion directly to capture count for aggregation
                count = await self._delete_memories(
                    source_message_ids=message_ids,
                    run_ids=event.affected_run_ids
                )
                self._deleted_count = count

                # --- NEW: Physical Memory Cleanup ---
                try:
                    await self._cleanup_physical_memory(event)
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as pe:
                    logger.warning(f"[MemoryRewind] Physical cleanup warning: {pe}")

                # Report back to the main event
                event.results["memories"] = count
                logger.info(f"[MemoryRewind] Successfully purged {count} memories for thread {event.thread_id}")
            else:
                logger.debug(f"[MemoryRewind] No affected messages identified for thread {event.thread_id}")

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            error_msg = f"Memory cleanup failed: {e}"
            logger.error(f"[MemoryRewind] {error_msg}")
            event.errors.append(error_msg)
            event.success = False

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
        async with session_scope() as session:
            # Use sequence_number for standardized ID construction
            stmt = select(Message.id).where(Message.thread_id == thread_id)

            if target_message_id:
                # Resolve sequence from UUID
                stmt_target = select(Message.sequence_number).where(Message.id == target_message_id)
                res_target = await session.execute(stmt_target)
                target_seq = res_target.scalar_one_or_none()

                if target_seq is None:
                    logger.warning(f"[MemoryRewind] Target message {target_message_id} not found")
                    return []

                if include_target:
                    stmt = stmt.where(Message.sequence_number >= target_seq)
                else:
                    stmt = stmt.where(Message.sequence_number > target_seq)

            result = await session.execute(stmt)
            return [str(row.id) for row in result.all()]

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
                    results = await memory_manager.search_memories(
                        query="",
                        filters={"source_message_id": msg_id},
                        limit=100
                    )

                    for mem in results:
                        if await memory_manager.delete_memory(mem.id):
                            count += 1

                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.warning(f"[MemoryRewind] Failed to delete memories for msg {msg_id}: {e}")

            # Delete by run_id
            for run_id in run_ids:
                try:
                    results = await memory_manager.search_memories(
                        query="",
                        filters={"run_id": run_id},
                        limit=100
                    )
                    for mem in results:
                        if await memory_manager.delete_memory(mem.id):
                            count += 1
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.warning(f"[MemoryRewind] Failed to delete memories for run {run_id}: {e}")

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[MemoryRewind] Memory manager initialization failed: {e}")

        return count

    async def cleanup(self, message_ids: list[str], **kwargs) -> int:
        """Direct cleanup entry point (non-event-driven usage)."""
        run_ids = kwargs.get("run_ids", [])
        return await self._delete_memories(
            source_message_ids=message_ids,
            run_ids=run_ids
        )

    async def _cleanup_physical_memory(self, event: RewindRequestedEvent) -> None:
        """
        Cleanup physical memory files (MEMORY.md, context/)
        based on the target message time.
        """
        async with session_scope() as session:
            if event.target_message_id:
                stmt = select(Message.created_at).where(Message.id == event.target_message_id)
                res = await session.execute(stmt)
                target_time = res.scalar_one_or_none()
            else:
                # Fallback to current time if no target (should not happen in targeted rewind)
                target_time = datetime.utcnow()

        if not target_time:
            logger.warning("[MemoryRewind] Could not determine target time for physical cleanup")
            return

        # Normalize target_time to naive UTC for consistent comparison with file mtimes
        if target_time.tzinfo:
            target_time = target_time.replace(tzinfo=None)

        memory_root = Path(settings.BRAIN_MEMORY_ROOT)

        # 1. Cleanup context snapshots (*.md in context/)
        context_dir = memory_root / "context"
        if context_dir.exists():
            for f in context_dir.glob("*.md"):
                if datetime.fromtimestamp(f.stat().st_mtime) > target_time:
                    try:
                        f.unlink()
                        logger.debug(f"[MemoryRewind] Deleted stale context file: {f.name}")
                    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as exc:
                        logger.debug(f"[MemoryRewind] Failed to delete {f.name}: {exc}")

        # 2. Regenerate MEMORY.md (Tier 1)
        try:
            from app.core.memory.lifespan import MemoryLifespanManager
            if not MemoryLifespanManager.is_initialized():
                await MemoryLifespanManager.ainitialize()

            container = MemoryLifespanManager.get_container()
            # This will pull from the newly cleaned cold memory (Vector DB)
            await container.memory_manager.regenerate_memory_md()
            logger.info("[MemoryRewind] MEMORY.md regenerated successfully")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[MemoryRewind] Failed to regenerate MEMORY.md: {e}")

    def get_deleted_count(self) -> int:
        """Get the count of memories deleted in the last operation."""
        return self._deleted_count


@event_register()
class MemoryConversationCleanup:
    """
    Cleans up memory data when a conversation is deleted.
    """

    @event_subscribe(ConversationEventType.CONVERSATION_DELETED)
    async def on_conversation_deleted(self, event: ConversationDeletedEvent) -> None:
        thread_id = event.thread_id
        logger.info(f"[MemoryCleanup] Cleaning up memory data for thread {thread_id}")

        # 1. Clear in-memory caches
        from app.core.memory import memory_tracker, predictive_cache
        memory_tracker.clear_thread(thread_id)
        predictive_cache.clear_thread(thread_id)

        # 2. Clean up MemoryIndex DB records
        try:
            from app.core.memory.lifespan import MemoryLifespanManager
            if MemoryLifespanManager.is_initialized():
                container = MemoryLifespanManager.get_container()
                memory_manager = container.memory_manager
                if hasattr(memory_manager, '_engine') and memory_manager._engine:
                    await memory_manager._engine._db_delete_by_source_thread_id(thread_id)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[MemoryCleanup] MemoryIndex cleanup warning: {e}")

        logger.info(f"[MemoryCleanup] Memory cleanup done for thread {thread_id}")
