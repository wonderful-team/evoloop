"""
File Rewind Handler
===================

Handles file restoration when conversation is rewound.

This module provides event-driven file cleanup for the rewind system,
restoring files to their state before Agent modification.
"""

import logging
from pathlib import Path

from app.core.rewind.events import FilesCleanupEvent, RewindRequestedEvent
from app.core.rewind.events import RewindEventType
from sqlalchemy import delete, select

from app.core.events.base import AsyncEventBus
from app.core.events.decorators import event_register, event_subscribe
from app.infrastructure.database.sql.database import session_scope
from app.models.file_operation import FileOperation

logger = logging.getLogger(__name__)


@event_register()
class FileRewind:
    """Event-driven file restoration handler for rewind operations."""

    def __init__(self):
        self._reverted_count = 0

    @classmethod
    def register(cls, bus: AsyncEventBus) -> "FileRewind":
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
        Handle main rewind event - prepare file operations list.
        
        This is called when a rewind is requested. We query FileOperations
        and publish a FILES_CLEANUP event with the operations to revert.
        """
        if not event.revert_files:
            logger.debug("[FileRewind] File revert disabled, skipping")
            return
        
        try:
            # Query file operations for this thread
            file_ops = await self._find_file_operations(
                thread_id=event.thread_id,
                target_message_id=event.target_message_id,
                include_target=event.include_target
            )
            
            if file_ops:
                # Publish specific cleanup event
                from app.core.events import system_bus
                await system_bus.publish(FilesCleanupEvent(
                    thread_id=event.thread_id,
                    file_operations=file_ops
                ))
                logger.info(f"[FileRewind] Prepared {len(file_ops)} file operations for cleanup")
        except Exception as e:
            logger.error(f"[FileRewind] Failed to prepare file cleanup: {e}")

    @event_subscribe(RewindEventType.FILES_CLEANUP)
    async def _handle_files_cleanup(self, event: FilesCleanupEvent) -> None:
        """
        Handle specific file cleanup event.
        
        This performs the actual file restoration.
        """
        try:
            count = await self._revert_files(event.file_operations)
            self._reverted_count = count
            logger.info(f"[FileRewind] Reverted {count} files")
        except Exception as e:
            logger.error(f"[FileRewind] File cleanup failed: {e}")
            raise

    async def _find_file_operations(
        self,
        thread_id: str,
        target_message_id: str | None,
        include_target: bool
    ) -> list[dict]:
        """
        Find file operations to revert for the given thread.
        
        Args:
            thread_id: The thread ID
            target_message_id: The message to rewind to
            include_target: Whether to include the target message's operations
            
        Returns:
            List of file operation dicts
        """
        async with session_scope() as session:
            # Build query to find FileOperations
            stmt = select(FileOperation).where(FileOperation.thread_id == thread_id)
            
            if target_message_id:
                # Filter by message ID range

                target_id = int(target_message_id)
                
                if include_target:
                    # Include operations from target message and after
                    stmt = stmt.where(FileOperation.message_id >= target_id)
                else:
                    # Only operations after target message
                    stmt = stmt.where(FileOperation.message_id > target_id)
            
            stmt = stmt.order_by(FileOperation.created_at.desc())
            
            result = await session.execute(stmt)
            ops = result.scalars().all()
            
            # Convert to operation dicts
            file_operations = []
            for op in ops:
                file_operations.append({
                    "id": op.id,
                    "message_id": op.message_id,
                    "path": op.file_path,
                    "operation": op.operation,  # ADD, EDIT, DELETE
                    "backup_content": op.original_content,
                })
            
            return file_operations

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
                        
            except Exception as e:
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
