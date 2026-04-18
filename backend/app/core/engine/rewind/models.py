from typing import Any

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class RewindOperation(DynamicBaseModel):
    """Request parameters for a rewind operation."""
    thread_id: str
    target_message_id: str | None = None  # None = rewind to last human message
    include_target: bool = False          # Whether to delete the target message
    revert_files: bool = True             # Whether to revert file changes
    reset_state: bool = True              # Whether to reset LangGraph state
    reason: str = "user_request"          # Why the rewind was triggered


class RewindResult(DynamicBaseModel):
    """Result of a rewind operation."""
    status: str  # "success", "partial", "failed", "empty", "no_human_message_found"
    thread_id: str
    removed_message_count: int = 0
    reverted_file_count: int = 0
    removed_memory_count: int = 0
    removed_todo_count: int = 0
    removed_trace_count: int = 0
    checkpoint_id: str | None = None
    errors: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for API response."""
        return {
            "status": self.status,
            "thread_id": self.thread_id,
            "removed_count": self.removed_message_count,
            "files_reverted": self.reverted_file_count,
            "memory_removed": self.removed_memory_count,
            "todos_removed": self.removed_todo_count,
            "traces_removed": self.removed_trace_count,
            "checkpoint_id": self.checkpoint_id,
            "errors": self.errors if self.errors else None,
        }
