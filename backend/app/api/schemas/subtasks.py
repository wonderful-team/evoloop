"""API schemas for subtasks routes."""

from typing import Any, Optional

from pydantic import Field

from app.api.schemas.responses import BaseAPIResponse
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.schemas.base import TimestampedEntity


class SubtaskCreate(DynamicBaseModel):
    """Subtask creation request."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    priority: str = "medium"  # high/medium/low
    estimated_hours: int = 0

class TaskWithSubtasksCreate(DynamicBaseModel):
    """Create parent task with subtasks."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    priority: str = "medium"
    estimated_hours: int = 0
    subtasks: list[SubtaskCreate] = []
    analysis_id: Optional[str] = None  # Optional, can be dummy

class TaskProgressUpdate(DynamicBaseModel):
    """Task progress update."""
    status: Optional[str] = None  # pending/in_progress/completed/failed
    progress: Optional[int] = Field(None, ge=0, le=100)
    result: Optional[str] = None  # Execution result summary

class TaskTreeResponse(DynamicBaseModel, TimestampedEntity):
    """Task tree response."""
    id: str
    title: str
    description: str
    status: str
    progress: int
    priority: str
    estimated_hours: int
    is_parent: bool
    subtasks: list["TaskTreeResponse"] = []

class ExecutableTaskResponse(DynamicBaseModel):
    """Next executable task response."""
    id: str
    title: str
    description: str
    is_subtask: bool
    parent_title: Optional[str] = None

class TaskCreateResponse(BaseAPIResponse):
    """Response after creating a task with subtasks."""
    task: dict[str, Any]

class TaskTreeWrapperResponse(BaseAPIResponse):
    """Response wrapping a task tree."""
    task: dict[str, Any]

class NextTaskResponse(BaseAPIResponse):
    """Response for next executable task."""
    task: dict[str, Any] | None

class TaskFlatResponse(BaseAPIResponse):
    """Response for flattened task tree."""
    count: int
    tasks: list[dict[str, Any]]

class TaskListItem(DynamicBaseModel):
    """Item in root task list."""
    id: str
    title: str
    status: str
    progress: int
    priority: str
    has_subtasks: bool
    created_at: str | None

class TaskListResponse(BaseAPIResponse):
    """Response for listing root tasks."""
    count: int
    tasks: list[TaskListItem]
