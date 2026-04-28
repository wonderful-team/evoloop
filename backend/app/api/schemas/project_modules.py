"""API schemas for project_modules routes."""

from app.models.schemas.base import ScopedRequest


class TimesheetQuickAddRequest(ScopedRequest):
    project_id: int
    hours: float
    description: str
    work_type: str | None = "development"
