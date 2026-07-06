"""API schemas for project modules routes (budget, timesheet, statistics)."""

from app.models.schemas.base import ScopedRequest


class TimesheetQuickAddRequest(ScopedRequest):
    project_id: int
    hours: float
    description: str
    work_type: str | None = "development"


__all__ = [
    "TimesheetQuickAddRequest",
]
