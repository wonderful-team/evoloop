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

from pydantic import Field, model_validator

from app.core.config import settings
from app.core.engine.rewind.events import RewindEvent, RewindEventType, RewindRequestedEvent
from app.core.events.base import AsyncEventBus
from app.core.events.decorators import event_register, event_subscribe
from app.infrastructure.database.resource_manager import db_resource_manager

logger = logging.getLogger(__name__)


class CheckpointCleanupEvent(RewindEvent):
    """Published to trigger checkpoint deletion from SQLite."""
    event_type: str = RewindEventType.CHECKPOINT_CLEANUP
    checkpoint_ids: list[str] = Field(default_factory=list)
    min_checkpoint_id: str | None = None

    @model_validator(mode="after")
    def _build_data(self):
        self.data = {
            "thread_id": self.thread_id,
            "checkpoint_ids": self.checkpoint_ids,
            "min_checkpoint_id": self.min_checkpoint_id,
            "count": len(self.checkpoint_ids),
        }
        return self


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

    @event_subscribe(RewindEventType.REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event: RewindRequestedEvent) -> None:
        """
        Handle main rewind event - prepare checkpoint cleanup.

        Determines the checkpoint range to delete and publishes cleanup event.
        """
        # Find checkpoints to delete based on message range
        checkpoint_info = await self._find_checkpoints_to_delete(
            thread_id=event.thread_id,
            target_message_id=event.target_message_id,
            include_target=event.include_target,
            reason=event.reason
        )

        if checkpoint_info:
            checkpoint_ids, min_checkpoint_id = checkpoint_info

            # Perform deletion directly to capture count for aggregation
            count = await self._delete_checkpoints(
                thread_id=event.thread_id,
                checkpoint_ids=checkpoint_ids
            )

            # Report back to the main event
            event.results["checkpoints"] = count

            # Still publish specific cleanup event for other potential listeners
            from app.core.events import system_bus
            await system_bus.publish(CheckpointCleanupEvent(
                thread_id=event.thread_id,
                checkpoint_ids=checkpoint_ids,
                min_checkpoint_id=min_checkpoint_id,
                delete_data=True
            ))
            logger.info(f"[CheckpointRewind] Deleted {count} checkpoints for thread {event.thread_id}")
        else:
            logger.debug(f"[CheckpointRewind] No checkpoints found to delete for thread {event.thread_id}")

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
            target_message_id: str | None,
            include_target: bool,
            reason: str = "user_request"
    ) -> tuple[list[str], str | None] | None:
        """Find checkpoint IDs to delete based on message range.

        For retry operations, deletes ALL checkpoints to ensure a clean slate.
        For targeted rewind, finds the checkpoint matching the target message.
        """
        async with db_resource_manager.get_raw_connection() as conn:
            try:
                # 1. Fetch checkpoints ordered by step (time), not checkpoint_id
                #    UUIDv7 is time-sortable, but json_extract(metadata, '$.step') is explicit.
                if settings.EMBEDDED_MODE:
                    query = (
                        f"SELECT checkpoint_id, metadata FROM checkpoints "
                        f"WHERE thread_id = {db_resource_manager.placeholder} "
                        f"ORDER BY CAST(json_extract(metadata, '$.step') AS INTEGER) DESC"
                    )
                    async with conn.execute(query, (thread_id,)) as cur:
                        rows = await cur.fetchall()
                else:
                    query = (
                        f"SELECT checkpoint_id, metadata FROM checkpoints "
                        f"WHERE thread_id = {db_resource_manager.placeholder} "
                        f"ORDER BY (metadata->>'step')::int DESC"
                    )
                    async with conn.cursor() as cur:
                        await cur.execute(query, (thread_id,))
                        rows = await cur.fetchall()

                if not rows:
                    return None

                import json
                all_ids = [row[0] for row in rows]
                # Build a list of (checkpoint_id, step, source, run_id)
                checkpoint_info = []
                for row in rows:
                    cp_id = row[0]
                    meta = row[1]
                    if isinstance(meta, str):
                        meta = json.loads(meta)
                    elif meta is None:
                        meta = {}
                    checkpoint_info.append({
                        "id": cp_id,
                        "step": meta.get("step", 0),
                        "source": meta.get("source", ""),
                        "run_id": meta.get("run_id", ""),
                    })

                # Retry mode: aggressively delete everything for a clean restart
                if reason == "retry" or not target_message_id:
                    if len(all_ids) <= 1:
                        return None
                    # Keep the oldest checkpoint (first in the list = smallest step)
                    # and delete everything else.
                    # Order was DESC, so reverse to get oldest first
                    oldest_id = checkpoint_info[-1]["id"]
                    ids_to_delete = [c["id"] for c in checkpoint_info[:-1]]
                    return (ids_to_delete, oldest_id) if ids_to_delete else None

                # Targeted rewind mode
                target_checkpoint = None
                # Checkpoints don't store message IDs. We can only match by
                # checkpoint_id containing the message id (unlikely for UUIDs)
                # or fall back to the most recent checkpoint.
                for c in checkpoint_info:
                    if target_message_id in c["id"] or c["id"] in target_message_id:
                        target_checkpoint = c["id"]
                        break

                if not target_checkpoint:
                    # Fallback: use the most recent checkpoint
                    target_checkpoint = checkpoint_info[0]["id"]

                try:
                    target_idx = all_ids.index(target_checkpoint)
                    ids_to_delete = all_ids[:target_idx + 1] if include_target else all_ids[:target_idx]
                except ValueError:
                    ids_to_delete = []

                return (ids_to_delete, target_checkpoint) if ids_to_delete else None

            except Exception as e:
                logger.warning(f"[CheckpointRewind] Failed to find checkpoints: {e}")
                return None

    async def _delete_checkpoints(
            self,
            thread_id: str,
            checkpoint_ids: list[str],
            min_checkpoint_id: str | None = None,
    ) -> int:
        """Delete checkpoints and associated writes from the active database."""
        if not checkpoint_ids and not min_checkpoint_id:
            return 0

        from app.core.config import settings
        async with db_resource_manager.get_raw_connection() as conn:
            try:
                writes_table = db_resource_manager.writes_table
                placeholder = db_resource_manager.placeholder

                deleted_checkpoints = 0
                deleted_writes = 0

                # 1. Disable constraints
                if settings.EMBEDDED_MODE:
                    await conn.execute("PRAGMA foreign_keys = OFF")

                # 2. Perform deletion
                if checkpoint_ids:
                    placeholders = ",".join(placeholder for _ in checkpoint_ids)
                    params = [thread_id] + checkpoint_ids

                    # Delete writes
                    delete_writes_sql = f"DELETE FROM {writes_table} WHERE thread_id = {placeholder} AND checkpoint_id IN ({placeholders})"
                    # Delete checkpoints
                    delete_cp_sql = f"DELETE FROM checkpoints WHERE thread_id = {placeholder} AND checkpoint_id IN ({placeholders})"

                    if not settings.EMBEDDED_MODE:
                        async with conn.cursor() as cur:
                            await cur.execute(delete_writes_sql, params)
                            deleted_writes = cur.rowcount
                            await cur.execute(delete_cp_sql, params)
                            deleted_checkpoints = cur.rowcount
                    else:
                        async with conn.execute(delete_writes_sql, params) as res:
                            deleted_writes = res.rowcount
                        async with conn.execute(delete_cp_sql, params) as res:
                            deleted_checkpoints = res.rowcount

                # 3. Cleanup Blobs (best effort)
                try:
                    blob_query = "DELETE FROM checkpoint_blobs"
                    if settings.EMBEDDED_MODE:
                        await conn.execute(blob_query)
                    else:
                        async with conn.cursor() as cur:
                            await cur.execute(blob_query)
                except Exception:
                    pass

                # 4. Finalize
                if settings.EMBEDDED_MODE:
                    await conn.execute("PRAGMA foreign_keys = ON")
                    await conn.commit()

                logger.info(f"[CheckpointRewind] Deleted {deleted_checkpoints} checkpoints and {deleted_writes} writes")
                return deleted_checkpoints

            except Exception as e:
                logger.error(f"[CheckpointRewind] Failed to delete checkpoints: {e}")
                return 0

    async def cleanup(
            self,
            thread_id: str,
            checkpoint_ids: list[str] | None = None,
            min_checkpoint_id: str | None = None,
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
