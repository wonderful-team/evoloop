"""
Batch Edit Tracker
==================

Tracks pending file edits and auto-creates checkpoints for batch operations.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class BatchEditTracker:
    """
    Tracks file edits within a context to detect batch operations.
    Auto-creates checkpoint when threshold is reached.
    
    Usage:
        async with batch_tracker.track_edit(file_path) as should_checkpoint:
            if should_checkpoint:
                # Auto-create checkpoint before batch
                await create_auto_checkpoint(thread_id, pending_files)
            # Perform edit
    """
    
    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self._pending_files: dict[str, list[str]] = {}  # thread_id -> file_paths
    
    def register_pending(self, thread_id: str, file_path: str) -> int:
        """
        Register a file as pending edit.
        
        Returns:
            Current count of pending files for this thread
        """
        if thread_id not in self._pending_files:
            self._pending_files[thread_id] = []
        
        # Avoid duplicates
        if file_path not in self._pending_files[thread_id]:
            self._pending_files[thread_id].append(file_path)
        
        return len(self._pending_files[thread_id])
    
    def get_pending(self, thread_id: str) -> list[str]:
        """Get list of pending files for a thread."""
        return self._pending_files.get(thread_id, []).copy()
    
    def clear_pending(self, thread_id: str):
        """Clear pending files after checkpoint created."""
        if thread_id in self._pending_files:
            del self._pending_files[thread_id]
    
    def should_create_checkpoint(self, thread_id: str) -> bool:
        """Check if we have enough pending files to warrant a checkpoint."""
        pending_count = len(self._pending_files.get(thread_id, []))
        return pending_count >= self.threshold


# Global instance
batch_tracker = BatchEditTracker()


async def maybe_create_auto_checkpoint(
    thread_id: str,
    file_path: str,
    project_id: int | None = None
) -> tuple[bool, str]:
    """
    Check if we should auto-create a checkpoint before editing.
    
    Args:
        thread_id: Current conversation thread
        file_path: File about to be edited
        project_id: Optional project context
    
    Returns:
        (created: bool, message: str)
    """
    from app.core.checkpoint.manager import checkpoint_manager
    
    # Register this file
    pending_count = batch_tracker.register_pending(thread_id, file_path)
    
    # Check if threshold reached and we haven't created one yet
    if batch_tracker.should_create_checkpoint(thread_id):
        # Get all pending files
        pending_files = batch_tracker.get_pending(thread_id)
        
        try:
            checkpoint = await checkpoint_manager.create_checkpoint(
                thread_id=thread_id,
                name=f"Auto: Before batch edit ({len(pending_files)} files)",
                file_paths=pending_files,
                description=f"Auto-created before editing {len(pending_files)} files",
                project_id=project_id,
                created_by="auto"
            )
            
            # Clear pending after creation
            batch_tracker.clear_pending(thread_id)
            
            logger.info(f"Auto-created checkpoint {checkpoint.id} for batch edit")
            return True, f"Auto-created checkpoint #{checkpoint.id}"
            
        except Exception as e:
            logger.error(f"Failed to auto-create checkpoint: {e}")
            return False, f"Failed to create checkpoint: {e}"
    
    return False, ""
