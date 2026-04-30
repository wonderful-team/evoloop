"""
Rewind Event Schemas
====================

Pydantic data classes for rewind/rollback events.
"""

from pydantic import Field, model_validator

from app.core.events.base import BaseEvent
from .types import RewindEventType


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
    event_type: str = "rewind.requested"
    target_message_id: str | None = None
    include_target: bool = False
    revert_files: bool = True
    reset_state: bool = True
    reason: str = "user_request"
    results: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    success: bool = True
    # Pre-computed message IDs affected by this rewind.
    # Populated by RewindOrchestrator so handlers do not race
    # against each other querying the messages table.
    affected_message_ids: list[str] = Field(default_factory=list)
    affected_db_message_ids: list[str] = Field(default_factory=list)
    affected_run_ids: list[str] = Field(default_factory=list)

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
    event_type: str = "rewind.completed"
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
    event_type: str = "rewind.failed"
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


class MessagesCleanupEvent(RewindEvent):
    """Published to trigger message deletion."""
    event_type: str = RewindEventType.MESSAGES_CLEANUP
    message_ids: list[str] = Field(default_factory=list)
    delete_references: bool = True

    @model_validator(mode="after")
    def _build_data(self):
        self.data = {
            "thread_id": self.thread_id,
            "message_ids": self.message_ids,
            "count": len(self.message_ids),
        }
        return self
