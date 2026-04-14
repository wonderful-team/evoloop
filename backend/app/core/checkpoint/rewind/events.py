"""
Rewind/Rollback Event Types and Data Structures
===============================================

Event types and data classes for conversation rewinding operations.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.events.base import BaseEvent


class RewindEventType(str, Enum):
    """
    Rewind/Rollback event types.
    
    These events are published when conversation history needs to be rolled back.
    Each handler subscribes to specific event types to perform cleanup.
    """
    # Main rewind events
    REWIND_REQUESTED = "rewind.requested"           # Rewind operation initiated
    REWIND_COMPLETED = "rewind.completed"           # Rewind operation finished
    REWIND_FAILED = "rewind.failed"                 # Rewind operation failed
    
    # Domain-specific cleanup events
    MESSAGES_CLEANUP = "rewind.messages.cleanup"    # Delete messages
    FILES_CLEANUP = "rewind.files.cleanup"          # Revert file changes
    MEMORY_CLEANUP = "rewind.memory.cleanup"        # Delete memories
    TODO_CLEANUP = "rewind.todo.cleanup"            # Delete todos
    TRACE_CLEANUP = "rewind.trace.cleanup"          # Delete trace events
    CHECKPOINT_CLEANUP = "rewind.checkpoint.cleanup" # Cleanup checkpoint state
    
    # State reset events
    STATE_RESET = "rewind.state.reset"              # Reset LangGraph state
    BLACKBOARD_RESET = "rewind.blackboard.reset"    # Reset blackboard data


from pydantic import Field


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
    target_message_id: str | None = None  # None = rewind to last human message
    include_target: bool = False          # Whether to delete the target message
    revert_files: bool = True             # Whether to revert file changes
    reset_state: bool = True              # Whether to reset LangGraph state
    reason: str = "user_request"          # Why the rewind was triggered
    
    def model_post_init(self, __context: Any) -> None:
        self.event_type = RewindEventType.REWIND_REQUESTED
        self.data = {
            "thread_id": self.thread_id,
            "target_message_id": self.target_message_id,
            "include_target": self.include_target,
            "revert_files": self.revert_files,
            "reset_state": self.reset_state,
            "reason": self.reason,
        }


class MessagesCleanupEvent(RewindEvent):
    """Published to trigger message deletion."""
    message_ids: list[str] = Field(default_factory=list)
    delete_references: bool = True
    
    def model_post_init(self, __context: Any) -> None:
        self.event_type = RewindEventType.MESSAGES_CLEANUP
        self.data = {
            "thread_id": self.thread_id,
            "message_ids": self.message_ids,
            "count": len(self.message_ids),
        }


class FilesCleanupEvent(RewindEvent):
    """Published to trigger file restoration."""
    file_operations: list[dict] = Field(default_factory=list)
    # Each dict: {"path": str, "operation": "ADD|EDIT|DELETE", "backup_content": str|None}
    
    def model_post_init(self, __context: Any) -> None:
        self.event_type = RewindEventType.FILES_CLEANUP
        self.data = {
            "thread_id": self.thread_id,
            "operation_count": len(self.file_operations),
        }


class MemoryCleanupEvent(RewindEvent):
    """Published to trigger memory deletion."""
    source_message_ids: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    
    def model_post_init(self, __context: Any) -> None:
        self.event_type = RewindEventType.MEMORY_CLEANUP
        self.data = {
            "thread_id": self.thread_id,
            "source_message_ids": self.source_message_ids,
            "run_ids": self.run_ids,
        }


class StateResetEvent(RewindEvent):
    """Published to trigger LangGraph state reset."""
    checkpoint_id: str | None = None
    reset_blackboard: bool = True
    reset_iteration_count: bool = True

    def model_post_init(self, __context: Any) -> None:
        self.event_type = RewindEventType.STATE_RESET
        self.data = {
            "thread_id": self.thread_id,
            "checkpoint_id": self.checkpoint_id,
            "reset_blackboard": self.reset_blackboard,
            "reset_iteration_count": self.reset_iteration_count,
        }


class CheckpointCleanupEvent(RewindEvent):
    """Published to trigger checkpoint deletion from SQLite."""
    checkpoint_ids: list[str] = Field(default_factory=list)
    min_checkpoint_id: str | None = None  # Alternative: delete all >= this ID

    def model_post_init(self, __context: Any) -> None:
        self.event_type = RewindEventType.CHECKPOINT_CLEANUP
        self.data = {
            "thread_id": self.thread_id,
            "checkpoint_ids": self.checkpoint_ids,
            "min_checkpoint_id": self.min_checkpoint_id,
            "count": len(self.checkpoint_ids),
        }


class TodoCleanupEvent(RewindEvent):
    """Published to trigger todo item deletion."""
    source_message_ids: list[str] = Field(default_factory=list)
    
    def model_post_init(self, __context: Any) -> None:
        self.event_type = RewindEventType.TODO_CLEANUP
        self.data = {
            "thread_id": self.thread_id,
            "source_message_ids": self.source_message_ids,
            "count": len(self.source_message_ids),
        }


class TraceCleanupEvent(RewindEvent):
    """Published to trigger trace event deletion."""
    source_message_ids: list[str] = Field(default_factory=list)
    
    def model_post_init(self, __context: Any) -> None:
        self.event_type = RewindEventType.TRACE_CLEANUP
        self.data = {
            "thread_id": self.thread_id,
            "source_message_ids": self.source_message_ids,
            "count": len(self.source_message_ids),
        }


class RewindCompletedEvent(RewindEvent):
    """Published when rewind operation completes successfully."""
    removed_message_count: int = 0
    reverted_file_count: int = 0
    removed_memory_count: int = 0
    new_checkpoint_id: str | None = None
    
    def model_post_init(self, __context: Any) -> None:
        self.event_type = RewindEventType.REWIND_COMPLETED
        self.data = {
            "thread_id": self.thread_id,
            "removed_message_count": self.removed_message_count,
            "reverted_file_count": self.reverted_file_count,
            "removed_memory_count": self.removed_memory_count,
            "new_checkpoint_id": self.new_checkpoint_id,
        }


class RewindFailedEvent(RewindEvent):
    """Published when rewind operation fails."""
    error: str = ""
    failed_step: str = "unknown"
    partial_results: dict = Field(default_factory=dict)
    
    def model_post_init(self, __context: Any) -> None:
        self.event_type = RewindEventType.REWIND_FAILED
        self.data = {
            "thread_id": self.thread_id,
            "error": self.error,
            "failed_step": self.failed_step,
            "partial_results": self.partial_results,
        }
