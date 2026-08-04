"""
Data models for background task management.
"""

import asyncio
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field

from app.core.tools.schemas import TaskMetadata, TaskStatus, TaskType
from app.infrastructure.pydantic_base import DynamicBaseModel


class BackgroundTask(DynamicBaseModel):
    """
    Represents a background task instance.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Identity
    task_id: str
    task_type: TaskType

    # State
    status: TaskStatus = TaskStatus.PENDING
    title: str = ""
    description: str = ""

    # Ownership
    tool_name: str = ""
    thread_id: str = ""
    project_id: int | None = None

    # Execution
    process_id: int | None = None
    timeout_seconds: int = 3600  # Default 1 hour max

    # Timing
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Output
    output_buffer: deque = Field(default_factory=lambda: deque(maxlen=1000))
    result: Any = None
    error_message: str | None = None

    # Extension point for tool-specific data
    metadata: TaskMetadata = Field(default_factory=TaskMetadata)

    # Internal: cancellation callback
    cancel_fn: Callable[[], None] | None = Field(default=None, exclude=True)

    def to_dict(self, include_output: bool = True, output_lines: int = 50) -> dict:
        """Convert to dictionary for API responses."""
        from app.core.tools.registry import get_tool_metadata

        data = self.model_dump()
        # Convert deque to list for JSON serialization
        if "output_buffer" in data:
            data["output_buffer"] = list(data["output_buffer"])

        # Override timing to string
        data["created_at"] = self.created_at.isoformat()
        data["started_at"] = self.started_at.isoformat() if self.started_at else None
        data["completed_at"] = self.completed_at.isoformat() if self.completed_at else None

        # Add derived properties
        data["elapsed_seconds"] = self.elapsed_seconds
        data["is_completed"] = self.is_completed
        data["is_running"] = self.is_running
        data["can_cancel"] = self.can_cancel
        data["task_type"] = self.task_type.value
        data["status"] = self.status.value

        # Resolve Display Title (Summary)
        display_title = self.title
        if self.tool_name:
            try:
                metadata = get_tool_metadata(self.tool_name)
                # Use metadata from the task as context for the template
                summary_args = {**self.metadata.model_dump(), "title": self.title}
                # If result is available and is a dict, merge it
                if isinstance(self.result, dict):
                    summary_args.update({k.lower(): v for k, v in self.result.items()})

                display_title = metadata.get_display_name(self.tool_name, summary_args)
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"Failed to resolve display title for {self.tool_name}: {e}")
        
        data["display_title"] = display_title
        # Keep title as-is but also provide the rendered one for UI
        if self.title.startswith("evoloop.tool_summary."):
            data["title"] = display_title

        if include_output:
            data["output"] = self.get_recent_output(output_lines)
            data["output_line_count"] = len(self.output_buffer)

        if self.error_message:
            data["error_message"] = self.error_message

        if self.result is not None:
            data["result"] = self._serialize_result()

        return data

    def get_recent_output(self, n: int = 50) -> str:
        """Get last n lines of output."""
        lines = list(self.output_buffer)
        return "\n".join(lines[-n:])

    def append_output(self, output: str) -> None:
        """Append output line(s)."""
        if output:
            self.output_buffer.append(output.rstrip("\n"))

    @property
    def elapsed_seconds(self) -> int:
        """Calculate elapsed time."""
        end_time = self.completed_at or datetime.now()
        start_time = self.started_at or self.created_at
        return int((end_time - start_time).total_seconds())

    @property
    def is_completed(self) -> bool:
        """Check if task is in a terminal state."""
        return self.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.TIMEOUT,
        }

    @property
    def is_running(self) -> bool:
        """Check if task is actively running."""
        return self.status == TaskStatus.RUNNING

    @property
    def can_cancel(self) -> bool:
        """Check if task can be cancelled."""
        return self.status in {TaskStatus.PENDING, TaskStatus.RUNNING}

    def _serialize_result(self) -> Any:
        """Safely serialize result."""
        if isinstance(self.result, (str, int, float, bool, type(None))):
            return self.result
        if isinstance(self.result, dict):
            return self.result
        if isinstance(self.result, list):
            return self.result[:100]  # Limit array size
        return str(self.result)[:1000]  # Fallback to string

    def set_cancel_callback(self, callback: Callable[[], None]) -> None:
        """Set callback for cancellation."""
        self.cancel_fn = callback

    async def cancel(self) -> bool:
        """
        Cancel this task.

        Returns:
            True if cancellation was initiated, False otherwise.
        """
        if not self.can_cancel:
            return False

        self.status = TaskStatus.CANCELLED

        if self.cancel_fn:
            try:
                if asyncio.iscoroutinefunction(self.cancel_fn):
                    await self.cancel_fn()
                else:
                    self.cancel_fn()
            except (TypeError, ValueError, RuntimeError, OSError) as e:
                # Log but don't fail
                import logging

                logging.getLogger(__name__).warning(f"Cancel callback failed: {e}")

        self.completed_at = datetime.now()
        return True
