"""
File Event Subscribers
======================

Event subscribers for file lifecycle and rewind operations.
"""

import logging
from pathlib import Path

from app.core.engine.rewind import REWIND_REQUESTED, RewindRequestedEvent
from app.core.engine.rewind.event import RewindEventType
from app.core.events.base import AsyncEventBus
from app.core.events.decorators import (
    event_register,
    event_subscribe,
    register_instance_handlers,
)

logger = logging.getLogger(__name__)


@event_register()
class FileRewind:
    """File restoration handler for rewind operations."""

    def __init__(self):
        self._reverted_count = 0

    @event_subscribe(REWIND_REQUESTED)
    async def _handle_rewind_requested(self, event: RewindRequestedEvent) -> None:
        if not event.revert_files:
            logger.debug("[FileRewind] File revert disabled, skipping")
            return

        target_ids = event.affected_message_ids
        if target_ids:
            file_ops = await self._find_file_operations_by_message_ids(
                thread_id=event.thread_id,
                message_ids=target_ids,
                run_ids=event.affected_run_ids
            )
        else:
            file_ops = await self._find_file_operations(
                thread_id=event.thread_id,
                target_message_id=event.target_message_id,
                include_target=event.include_target
            )

        if file_ops:
            count = await self._revert_files(file_ops)
            self._reverted_count = count
            event.results["files"] = count

            db_count = await self._cleanup_database_records(file_ops)
            logger.info(f"[FileRewind] Reverted {count} files, cleaned {db_count} DB records for thread {event.thread_id}")
        else:
            logger.info(f"[FileRewind] No file operations to revert for thread {event.thread_id}")

    async def _find_file_operations(
        self,
        thread_id: str,
        target_message_id: str | None,
        include_target: bool
    ) -> list[dict]:
        """Find file operations to revert for the given thread."""
        from sqlalchemy import select

        from app.infrastructure.database import session_scope
        from app.models import Message
        from app.models.file_operation import FileOperation

        async with session_scope() as session:
            stmt = select(FileOperation).where(FileOperation.thread_id == thread_id)

            if target_message_id:
                # Resolve sequence from UUID
                stmt_target = select(Message.sequence_number).where(Message.id == target_message_id)
                res_target = await session.execute(stmt_target)
                target_seq = res_target.scalar_one_or_none()

                if target_seq is None:
                    logger.warning(f"[FileRewind] Target message {target_message_id} not found")
                    return []

                if include_target:
                    stmt = stmt.where(FileOperation.message_id.in_(
                        select(Message.id).where(Message.thread_id == thread_id, Message.sequence_number >= target_seq)
                    ))
                else:
                    stmt = stmt.where(FileOperation.message_id.in_(
                        select(Message.id).where(Message.thread_id == thread_id, Message.sequence_number > target_seq)
                    ))

            stmt = stmt.order_by(FileOperation.created_at.desc())
            result = await session.execute(stmt)
            ops = result.scalars().all()

            return [{
                "id": op.id,
                "message_id": op.message_id,
                "path": op.file_path,
                "operation": op.operation,
                "backup_content": op.original_content,
            } for op in ops]

    async def _find_file_operations_by_message_ids(
        self,
        thread_id: str,
        message_ids: list[str] | None = None,
        run_ids: list[str] | None = None
    ) -> list[dict]:
        """Find file operations by message IDs or run IDs."""
        if not message_ids and not run_ids:
            return []

        from sqlalchemy import or_, select

        from app.infrastructure.database import session_scope
        from app.models.file_operation import FileOperation

        async with session_scope() as session:
            stmt = select(FileOperation).where(FileOperation.thread_id == thread_id)

            conditions = []
            if message_ids:
                conditions.append(FileOperation.message_id.in_(message_ids))
            if run_ids:
                conditions.append(FileOperation.run_id.in_(run_ids))

            if len(conditions) > 1:
                stmt = stmt.where(or_(*conditions))
            else:
                stmt = stmt.where(conditions[0])

            stmt = stmt.order_by(FileOperation.created_at.desc())
            result = await session.execute(stmt)
            ops = result.scalars().all()

            return [{
                "id": op.id,
                "message_id": op.message_id,
                "path": op.file_path,
                "operation": op.operation,
                "backup_content": op.original_content,
            } for op in ops]

    async def _revert_files(self, file_operations: list[dict]) -> int:
        """
        Perform physical file restoration.
        
        Args:
            file_operations: List of file operation dicts
            
        Returns:
            Number of files successfully reverted
        """
        count = 0

        # Process in reverse chronological order (last-modified first)
        for op in sorted(file_operations, key=lambda x: x.get("created_at", ""), reverse=True):
            try:
                path = Path(op["path"])
                operation = op["operation"]

                if operation == "ADD":
                    # File was created -> delete it
                    if path.exists():
                        path.unlink()
                        logger.info(f"🔙 Undo ADD: Deleted {op['path']}")
                        count += 1

                elif operation in ("EDIT", "DELETE"):
                    # File was modified/deleted -> restore original content
                    backup_content = op.get("backup_content")
                    if backup_content is not None:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(backup_content, encoding="utf-8")
                        logger.info(f"🔙 Undo {operation}: Restored {op['path']}")
                        count += 1
                    else:
                        logger.warning(f"⚠️ Cannot undo {operation} for {op['path']}: no backup")

            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.error(f"❌ Undo failed for {op.get('path', 'unknown')}: {e}")

        return count

    async def _cleanup_database_records(self, file_operations: list[dict]) -> int:
        """
        Clean up FileOperation database records.
        
        Args:
            file_operations: List of file operation dicts
            
        Returns:
            Number of records deleted
        """
        if not file_operations:
            return 0

        from sqlalchemy import delete

        from app.infrastructure.database import session_scope
        from app.models.file_operation import FileOperation

        operation_ids = [op["id"] for op in file_operations if "id" in op]

        async with session_scope() as session:
            result = await session.execute(
                delete(FileOperation).where(FileOperation.id.in_(operation_ids))
            )
            deleted_count = result.rowcount
            logger.info(f"🗑️ Cleaned {deleted_count} FileOperation records")
            return deleted_count

    async def cleanup(self, message_ids: list[str], **kwargs) -> int:
        """Direct cleanup entry point (non-event-driven usage)."""
        revert_files = kwargs.get("revert_files", True)

        if not revert_files:
            return 0

        from sqlalchemy import select

        from app.infrastructure.database import session_scope
        from app.models.file_operation import FileOperation

        # Convert message IDs to file operations
        async with session_scope() as session:
            stmt = select(FileOperation).where(FileOperation.message_id.in_(message_ids))
            result = await session.execute(stmt)
            ops = result.scalars().all()

            if not ops:
                return 0

            # Convert to operation dicts
            file_operations = []
            for op in ops:
                file_operations.append({
                    "id": op.id,
                    "path": op.file_path,
                    "operation": op.operation,
                    "backup_content": op.original_content,
                })

        # Perform restoration
        count = await self._revert_files(file_operations)

        # Clean up database records
        await self._cleanup_database_records(file_operations)

        return count

    def get_reverted_count(self) -> int:
        """Get the count of files reverted in the last operation."""
        return self._reverted_count

    @event_subscribe(RewindEventType.FILES_CLEANUP)
    async def _handle_files_cleanup(self, event) -> None:
        """Helper to test file reverting with a mock event list directly."""
        from app.core.file.event.schemas import FilesCleanupEvent
        if not isinstance(event, FilesCleanupEvent):
            return
        if event.file_operations:
            count = await self._revert_files(event.file_operations)
            self._reverted_count = count
