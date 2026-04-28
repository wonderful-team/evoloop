"""API schemas for project_modules routes."""

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.api.schemas.responses import BaseAPIResponse, ListResponse
from app.models.schemas.base import ScopedRequest
from typing import Any, Optional

class TimesheetQuickAddRequest(ScopedRequest):
    project_id: int
    hours: float
    description: str
    work_type: str | None = "development"
