"""
Checkpoint Rewind Handler
=========================

Handles LangGraph checkpoint cleanup when conversation is rewound.

This module provides cleanup for SQLite-based checkpoints (embedded mode),
including the `writes` table used by langgraph-checkpoint-sqlite.

Note: PostgreSQL version uses `checkpoint_writes` table, but EvoLoop
in embedded mode uses SQLite with `writes` table.
"""

import logging
from typing import Optional

import aiosqlite

from app.core.events.decorators import event_register, event_subscribe
from app.core.events.base import AsyncEventBus
from app.core.persistence import get_checkpointer
from app.core.checkpoint.rewind.events import (
    CheckpointCleanupEvent,
    RewindEventType,
    RewindRequestedEvent,
)

logger = logging.getLogger(__name__)


@event_register()
class CheckpointRewind:
    """
    Event-driven checkpoint cleanup handler for rewind operations.

    Handles deletion of LangGraph checkpoint data from SQLite:
    - checkpoints table: Main checkpoint records
    - writes table: Task writes (langgraph-checkpoint-sqlite)
    - checkpoint_blobs table: Blob storage
    """

    def __init__(self):
        self._deleted_checkpoints = 0
        self._deleted_writes = 0

    @classmethod
    def register(cls, bus: AsyncEventBus) -> "CheckpointRewind":
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

    def _get_db_path(self) -> Optional[str]:
        """Resolve the SQLite database path from the checkpointer."""
        try:
            cp = get_checkpointer()
            if cp is None:
                return None
            # AsyncSqliteSaver stores path in .conn or .db attrs
            if hasattr(cp, "conn") and isinstance(cp.conn, str):
                return cp.conn
            if hasattr(cp, "db"):
                return cp.db
        except Exception as e:
            logger.debug(f"[CheckpointRewind] Could not get db path: {e}")
        return None

    @event_subscribe(RewindEventType.REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event: RewindRequestedEvent) -> None:
        """
        Handle main rewind event - prepare checkpoint cleanup.

        Determines the checkpoint range to delete and publishes cleanup event.
        """
        try:
            # Find checkpoints to delete based on message range
            checkpoint_info = await self._find_checkpoints_to_delete(
                thread_id=event.thread_id,
                target_message_id=event.target_message_id,
                include_target=event.include_target
            )

            if checkpoint_info:
                checkpoint_ids, min_checkpoint_id = checkpoint_info
                from app.core.events import system_bus
                await system_bus.publish(CheckpointCleanupEvent(
                    thread_id=event.thread_id,
                    checkpoint_ids=checkpoint_ids,
                    min_checkpoint_id=min_checkpoint_id,
                ))
                logger.info(f"[CheckpointRewind] Prepared {len(checkpoint_ids)} checkpoints for cleanup")
            else:
                logger.debug(f"[CheckpointRewind] No checkpoints to delete for thread {event.thread_id}")

        except Exception as e:
            logger.error(f"[CheckpointRewind] Failed to prepare checkpoint cleanup: {e}")
            # Don't raise - checkpoint cleanup is best-effort

    @event_subscribe(RewindEventType.CHECKPOINT_CLEANUP)
    async def _handle_checkpoint_cleanup(self, event: CheckpointCleanupEvent) -> None:
        """
        Handle specific checkpoint cleanup event.

        Deletes checkpoint records from SQLite tables.
        """
        try:
            count = await self._delete_checkpoints(
                thread_id=event.thread_id,
                checkpoint_ids=event.checkpoint_ids,
                min_checkpoint_id=event.min_checkpoint_id,
            )
            self._deleted_checkpoints = count
            logger.info(f"[CheckpointRewind] Deleted {count} checkpoints and {self._deleted_writes} writes")
        except Exception as e:
            logger.error(f"[CheckpointRewind] Checkpoint cleanup failed: {e}")
            # Don't raise - checkpoint cleanup is best-effort

    async def _find_checkpoints_to_delete(
        self,
        thread_id: str,
        target_message_id: Optional[str],
        include_target: bool
    ) -> Optional[tuple[list[str], Optional[str]]]:
        """
        Find checkpoint IDs to delete based on message range.

        Strategy:
        1. Map message IDs to checkpoint IDs via metadata
        2. Find all checkpoints >= target checkpoint
        3. Return list of checkpoint IDs to delete

        Args:
            thread_id: The thread ID
            target_message_id: The message to rewind to
            include_target: Whether to include target's checkpoint

        Returns:
            Tuple of (checkpoint_ids_to_delete, min_checkpoint_id) or None
        """
        db_path = self._get_db_path()
        if not db_path:
            logger.debug("[CheckpointRewind] No SQLite checkpointer available")
            return None

        try:
            async with aiosqlite.connect(db_path) as conn:
                # Get all checkpoints for this thread, ordered by checkpoint_id
                async with conn.execute(
                    """
                    SELECT checkpoint_id, metadata
                    FROM checkpoints
                    WHERE thread_id = ?
                    ORDER BY checkpoint_id DESC
                    """,
                    (thread_id,)
                ) as cur:
                    rows = await cur.fetchall()

                if not rows:
                    return None

                # If we have a target message ID, we need to find the corresponding checkpoint
                # For now, we use a simple heuristic: checkpoint_id is often based on message sequence
                # A more accurate approach would parse metadata to find the exact checkpoint

                if target_message_id:
                    # Try to find checkpoint that contains this message
                    # checkpoint_id format varies, but often includes message number
                    target_checkpoint = None
                    for row in rows:
                        checkpoint_id = row[0]
                        # Try to match checkpoint_id with message_id
                        # checkpoint_id might be "msg-123" or contain "123"
                        if target_message_id in checkpoint_id or checkpoint_id in target_message_id:
                            target_checkpoint = checkpoint_id
                            break

                    if not target_checkpoint:
                        # Fallback: use the most recent checkpoint as target
                        # This means we won't delete the most recent state
                        target_checkpoint = rows[0][0]

                    # Find all checkpoints to delete
                    all_ids = [row[0] for row in rows]
                    try:
                        target_idx = all_ids.index(target_checkpoint)
                        if include_target:
                            ids_to_delete = all_ids[:target_idx + 1]
                        else:
                            ids_to_delete = all_ids[:target_idx]
                    except ValueError:
                        ids_to_delete = []

                    return (ids_to_delete, target_checkpoint) if ids_to_delete else None
                else:
                    # No target - keep only the most recent checkpoint
                    if len(rows) <= 1:
                        return None
                    all_ids = [row[0] for row in rows]
                    # Delete all except the most recent
                    return (all_ids[1:], all_ids[0])

        except Exception as e:
            logger.warning(f"[CheckpointRewind] Failed to find checkpoints: {e}")
            return None

    async def _delete_checkpoints(
        self,
        thread_id: str,
        checkpoint_ids: list[str],
        min_checkpoint_id: Optional[str] = None,
    ) -> int:
        """
        Delete checkpoints and associated writes from SQLite.

        Args:
            thread_id: The thread ID
            checkpoint_ids: List of checkpoint IDs to delete
            min_checkpoint_id: Minimum checkpoint ID (for range-based deletion)

        Returns:
            Number of checkpoints deleted
        """
        if not checkpoint_ids and not min_checkpoint_id:
            return 0

        db_path = self._get_db_path()
        if not db_path:
            logger.debug("[CheckpointRewind] No SQLite checkpointer available for deletion")
            return 0

        try:
            async with aiosqlite.connect(db_path) as conn:
                await conn.execute("PRAGMA foreign_keys = OFF")

                deleted_checkpoints = 0
                deleted_writes = 0

                if checkpoint_ids:
                    # Delete specific checkpoints
                    placeholders = ",".join("?" * len(checkpoint_ids))

                    # Delete from writes table first (langgraph-checkpoint-sqlite)
                    result = await conn.execute(
                        f"""
                        DELETE FROM writes
                        WHERE thread_id = ? AND checkpoint_id IN ({placeholders})
                        """,
                        [thread_id] + checkpoint_ids
                    )
                    deleted_writes = result.rowcount

                    # Delete from checkpoints table
                    result = await conn.execute(
                        f"""
                        DELETE FROM checkpoints
                        WHERE thread_id = ? AND checkpoint_id IN ({placeholders})
                        """,
                        [thread_id] + checkpoint_ids
                    )
                    deleted_checkpoints = result.rowcount

                elif min_checkpoint_id:
                    # Delete all checkpoints >= min_checkpoint_id
                    # Delete from writes table
                    result = await conn.execute(
                        """
                        DELETE FROM writes
                        WHERE thread_id = ? AND checkpoint_id >= ?
                        """,
                        (thread_id, min_checkpoint_id)
                    )
                    deleted_writes = result.rowcount

                    # Delete from checkpoints table
                    result = await conn.execute(
                        """
                        DELETE FROM checkpoints
                        WHERE thread_id = ? AND checkpoint_id >= ?
                        """,
                        (thread_id, min_checkpoint_id)
                    )
                    deleted_checkpoints = result.rowcount

                # Clean up orphaned blobs (if table exists)
                try:
                    await conn.execute("""
                        DELETE FROM checkpoint_blobs
                        WHERE version NOT IN (SELECT checkpoint_id FROM checkpoints)
                    """)
                except Exception:
                    # checkpoint_blobs table may not exist in some setups
                    pass

                await conn.execute("PRAGMA foreign_keys = ON")
                await conn.commit()

                self._deleted_writes = deleted_writes
                logger.info(
                    f"[CheckpointRewind] Deleted {deleted_checkpoints} checkpoints, "
                    f"{deleted_writes} writes from thread {thread_id}"
                )
                return deleted_checkpoints

        except Exception as e:
            logger.error(f"[CheckpointRewind] Failed to delete checkpoints: {e}")
            return 0

    async def cleanup(
        self,
        thread_id: str,
        checkpoint_ids: Optional[list[str]] = None,
        min_checkpoint_id: Optional[str] = None,
    ) -> int:
        """Direct cleanup entry point (non-event-driven usage)."""
        return await self._delete_checkpoints(
            thread_id=thread_id,
            checkpoint_ids=checkpoint_ids or [],
            min_checkpoint_id=min_checkpoint_id,
        )

    def get_deleted_counts(self) -> tuple[int, int]:
        """Get the counts of deleted checkpoints and writes."""
        return (self._deleted_checkpoints, self._deleted_writes)
