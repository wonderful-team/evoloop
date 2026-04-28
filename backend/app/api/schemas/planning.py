"""API schemas for planning routes."""

from app.api.schemas.responses import BaseAPIResponse
from app.infrastructure.pydantic_base import DynamicBaseModel


class PlanStepResponse(BaseAPIResponse):
    """Plan step item."""
    id: str
    title: str
    status: str
    result: str | None

class PlanDataResponse(DynamicBaseModel):
    """Nested plan data."""
    id: str
    title: str
    steps: list[PlanStepResponse]
    current_step_id: str | None

class PlanResponse(BaseAPIResponse):
    """Plan API response."""
    status: str
    plan: PlanDataResponse | None = None
    generated_at: str | None = None
    error: str | None = None
