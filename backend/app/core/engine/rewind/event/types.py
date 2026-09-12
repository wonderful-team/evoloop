from enum import Enum

from app.constants import MESSAGES_CLEANUP, REWIND_REQUESTED


class RewindEventType(str, Enum):
    """Event types emitted during conversation rewind operations."""

    REWIND_REQUESTED = REWIND_REQUESTED
    REWIND_COMPLETED = "rewind.completed"
    REWIND_FAILED = "rewind.failed"
    MESSAGES_CLEANUP = MESSAGES_CLEANUP
    FILES_CLEANUP = "rewind.files.cleanup"
    MEMORY_CLEANUP = "rewind.memory.cleanup"
    TRACE_CLEANUP = "rewind.trace.cleanup"
    CHECKPOINT_CLEANUP = "rewind.checkpoint.cleanup"
