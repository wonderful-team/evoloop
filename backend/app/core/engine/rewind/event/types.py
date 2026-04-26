"""
Rewind Event Types
==================

Event type constants for conversation rewind/rollback operations.
"""

from enum import Enum


class RewindEventType(str, Enum):
    """
    Rewind/Rollback event types.

    These event type constants are centralized so the orchestrator
    and cross-domain code can reference them uniformly.
    Domain-specific event *classes* live in their respective modules.
    """
    # Main rewind events
    REWIND_REQUESTED = "rewind.requested"
    REWIND_COMPLETED = "rewind.completed"
    REWIND_FAILED = "rewind.failed"

    # Domain-specific cleanup events
    MESSAGES_CLEANUP = "rewind.messages.cleanup"
    FILES_CLEANUP = "rewind.files.cleanup"
    MEMORY_CLEANUP = "rewind.memory.cleanup"
    TODO_CLEANUP = "rewind.todo.cleanup"
    TRACE_CLEANUP = "rewind.trace.cleanup"
    CHECKPOINT_CLEANUP = "rewind.checkpoint.cleanup"
