"""
Rewind/Rollback Event Types and Data Structures
===============================================

Core event types and data classes for conversation rewinding operations.

Domain-specific cleanup events (e.g. FilesCleanupEvent, MemoryCleanupEvent)
are defined in their respective domain modules to maintain boundary integrity.
"""

from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from app.core.events.base import BaseEvent


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


class RewindEvent(BaseEvent):
    """Base class for all rewind events."""
    source: str = "rewind_service"
    thread_id: str = ""


class RewindRequestedEvent(RewindEvent):
    """
    Published when a rewind operation is requested.

    This is the entry point - all handlers should listen to this event
    to determine if they need to take action.
    """
    event_type: str = RewindEventType.REWIND_REQUESTED
    target_message_id: str | None = None
    include_target: bool = False
    revert_files: bool = True
    reset_state: bool = True
    reason: str = "user_request"
    results: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    success: bool = True

    @model_validator(mode="after")
    def _build_data(self):
        self.data = {
            "thread_id": self.thread_id,
            "target_message_id": self.target_message_id,
            "include_target": self.include_target,
            "revert_files": self.revert_files,
            "reset_state": self.reset_state,
            "reason": self.reason,
            "results": self.results,
            "errors": self.errors,
            "success": self.success,
        }
        return self


class RewindCompletedEvent(RewindEvent):
    """Published when rewind operation completes successfully."""
    event_type: str = RewindEventType.REWIND_COMPLETED
    removed_message_count: int = 0
    reverted_file_count: int = 0
    removed_memory_count: int = 0
    new_checkpoint_id: str | None = None

    @model_validator(mode="after")
    def _build_data(self):
        self.data = {
            "thread_id": self.thread_id,
            "removed_message_count": self.removed_message_count,
            "reverted_file_count": self.reverted_file_count,
            "removed_memory_count": self.removed_memory_count,
            "new_checkpoint_id": self.new_checkpoint_id,
        }
        return self


class RewindFailedEvent(RewindEvent):
    """Published when rewind operation fails."""
    event_type: str = RewindEventType.REWIND_FAILED
    error: str = ""
    failed_step: str = "unknown"
    partial_results: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _build_data(self):
        self.data = {
            "thread_id": self.thread_id,
            "error": self.error,
            "failed_step": self.failed_step,
            "partial_results": self.partial_results,
        }
        return self
