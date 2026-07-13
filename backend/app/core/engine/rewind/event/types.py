from enum import Enum


class RewindEventType(str, Enum):
    """Event types emitted during conversation rewind operations."""
    REWIND_REQUESTED = "rewind.requested"
    REWIND_COMPLETED = "rewind.completed"
    REWIND_FAILED = "rewind.failed"
    MESSAGES_CLEANUP = "rewind.messages.cleanup"
    FILES_CLEANUP = "rewind.files.cleanup"
    MEMORY_CLEANUP = "rewind.memory.cleanup"
    TODO_CLEANUP = "rewind.todo.cleanup"
    TRACE_CLEANUP = "rewind.trace.cleanup"
    CHECKPOINT_CLEANUP = "rewind.checkpoint.cleanup"
