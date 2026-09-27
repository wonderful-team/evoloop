"""Core engine schemas — graph config, execution results, and operational models."""

from typing import Any

from pydantic import BaseModel, Field

from app.infrastructure.pydantic_base import DynamicBaseModel

# ---------------------------------------------------------------------------
# Error Handling (from error_handler.py)
# ---------------------------------------------------------------------------


class ErrorClassification(BaseModel):
    """Structured error classification result."""

    error_type: str
    status_code: int | None = None
    title: str
    message: str
    hint: str
    raw_error: str
    is_terminal: bool = False


# ---------------------------------------------------------------------------
# Context Monitoring (from context_monitor.py)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Rewind Operations (from rewind/models.py)
# ---------------------------------------------------------------------------


class RewindResult(DynamicBaseModel):
    """Result of a rewind operation."""

    status: str
    thread_id: str
    removed_message_count: int = 0
    reverted_file_count: int = 0
    removed_memory_count: int = 0
    removed_trace_count: int = 0
    checkpoint_id: str | None = None
    errors: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "thread_id": self.thread_id,
            "removed_count": self.removed_message_count,
            "files_reverted": self.reverted_file_count,
            "memory_removed": self.removed_memory_count,
            "traces_removed": self.removed_trace_count,
            "checkpoint_id": self.checkpoint_id,
            "errors": self.errors if self.errors else None,
        }
