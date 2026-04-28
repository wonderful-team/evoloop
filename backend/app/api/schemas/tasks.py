"""API schemas for tasks routes."""

from typing import Any

from app.api.schemas.responses import BaseAPIResponse
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.schemas.base import ScopedRequest


class TaskCreateRequest(ScopedRequest):
    project_id: int
    task_title: str
    task_desc: str | None = ""
    priority: int = 2
    match_score: float | None = None
    relevance_analysis: str | None = None
    key_modules: Any | None = None
    technical_challenges: Any | None = None
    implementation_complexity: str | None = None
    deliverables: Any | None = None

class TaskUpdateRequest(DynamicBaseModel):
    task_title: str | None = None
    task_desc: str | None = None
    priority: int | None = None
    status: int | None = None
    progress: int | None = None
    # AI fields are also updateable
    match_score: float | None = None
    relevance_analysis: str | None = None
    key_modules: Any | None = None
    technical_challenges: Any | None = None
    implementation_complexity: str | None = None
    deliverables: Any | None = None

class TaskStatusUpdate(DynamicBaseModel):
    status: int
    progress: int | None = 0

class TaskExecutionResponse(BaseAPIResponse):
    status: str
    thread_id: str
