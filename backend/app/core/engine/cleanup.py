
import logging
from pathlib import Path
from typing import List

from sqlalchemy import delete, select

from app.core.memory import memory_manager
from app.infrastructure.database.sql.database import session_scope
from app.models.todo import TodoItem
from app.models.file_operation import FileOperation
from app.core.interfaces.cleanup import ICleanupHandler
from app.core.brain.cleanup import BrainCleanupHandler

logger = logging.getLogger(__name__)


class FileUndoHandler(ICleanupHandler):
    """
    Handles physical file restoration when user requests Undo.
    Restores files to their state before Agent modification.
    """
    
    async def cleanup(self, message_ids: List[str], revert_files: bool = True) -> int:
        count = 0
        async with session_scope() as session:
            # 1. Query FileOperations linked to these messages
            stmt = select(FileOperation).where(FileOperation.message_id.in_(message_ids))
            result = await session.execute(stmt)
            ops = result.scalars().all()
            
            if not ops:
                return 0
            
            # 2. Physical Restoration (if requested)
            if revert_files:
                # Process in reverse chronological order (last-modified first)
                for op in sorted(ops, key=lambda x: x.created_at, reverse=True):
                    try:
                        path = Path(op.file_path)
                        
                        if op.operation == "ADD":
                            # File was created -> delete it
                            if path.exists():
                                path.unlink()
                                logger.info(f"🔙 Undo ADD: Deleted {op.file_path}")
                        
                        elif op.operation in ("EDIT", "DELETE"):
                            # File was modified/deleted -> restore original content
                            if op.original_content is not None:
                                path.parent.mkdir(parents=True, exist_ok=True)
                                path.write_text(op.original_content, encoding="utf-8")
                                logger.info(f"🔙 Undo {op.operation}: Restored {op.file_path}")
                            else:
                                logger.warning(f"⚠️ Cannot undo {op.operation} for {op.file_path}: no backup")
                        
                        count += 1
                    except Exception as e:
                        logger.error(f"❌ Undo failed for {op.file_path}: {e}")
            
            # 3. Always clean up database records
            await session.execute(
                delete(FileOperation).where(FileOperation.message_id.in_(message_ids))
            )
            logger.info(f"🗑️ Cleaned {len(ops)} FileOperation records")
        
        return count


class CleanupOrchestrator:
    """
    Central registry for cleanup handlers.
    Delegates cleanup of side effects to registered modules.
    """
    
    def __init__(self):
        self.handlers: List[ICleanupHandler] = []
        self.file_undo_handler = FileUndoHandler()
        self._register_default_handlers()

    def _register_default_handlers(self):
        # 1. Brain Module Handler
        try:
            self.handlers.append(BrainCleanupHandler())
        except Exception as e:
            logger.error(f"Failed to register BrainCleanupHandler: {e}")

        # 2. Episode Handler (Memory Module)
        class EpisodeCleanupHandler(ICleanupHandler):
            async def cleanup(self, message_ids: List[str], **kwargs) -> int:
                try:
                    return await memory_manager.long_term.delete_episodes_by_message_ids(message_ids)
                except Exception as e:
                    logger.error(f"Episode cleanup failed: {e}")
                    return 0
        
        self.handlers.append(EpisodeCleanupHandler())

        # 3. Todo Handler (Domain/Engine Module)
        class TodoCleanupHandler(ICleanupHandler):
            async def cleanup(self, message_ids: List[str], **kwargs) -> int:
                try:
                    async with session_scope() as session:
                        stmt = delete(TodoItem).where(TodoItem.source_message_id.in_(message_ids))
                        result = await session.execute(stmt)
                        return result.rowcount
                except Exception as e:
                    logger.error(f"Todo cleanup failed: {e}")
                    return 0

        self.handlers.append(TodoCleanupHandler())

    async def cleanup_all(self, message_ids: List[str], revert_files: bool = True) -> dict:
        if not message_ids:
            return {}

        logger.info(f"CleanupOrchestrator: Rolling back side effects for {len(message_ids)} messages (revert_files={revert_files})...")
        
        results = {}
        
        # 1. File Undo Handler (special, has revert_files flag)
        try:
            count = await self.file_undo_handler.cleanup(message_ids, revert_files=revert_files)
            results["FileUndoHandler"] = count
            logger.info(f"Handler FileUndoHandler cleaned {count} items.")
        except Exception as e:
            logger.error(f"Handler FileUndoHandler failed: {e}")
            results["FileUndoHandler"] = -1
        
        # 2. Other handlers
        for handler in self.handlers:
            name = handler.__class__.__name__
            try:
                count = await handler.cleanup(message_ids)
                results[name] = count
                logger.info(f"Handler {name} cleaned {count} items.")
            except Exception as e:
                logger.error(f"Handler {name} failed: {e}")
                results[name] = -1

        return results


# Singleton instance
_orchestrator = CleanupOrchestrator()


async def cleanup_side_effects(message_ids: List[str], revert_files: bool = True) -> dict:
    """
    Public entry point for cleanup.
    
    Args:
        message_ids: List of message IDs to clean up
        revert_files: If True, physically restore files to pre-modification state.
                      If False, only clean up DB records (leave files unchanged).
    """
    return await _orchestrator.cleanup_all(message_ids, revert_files=revert_files)
