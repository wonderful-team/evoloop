"""API schemas for project_profiles routes."""

from app.api.schemas.responses import BaseAPIResponse
from app.infrastructure.pydantic_base import DynamicBaseModel


class DiscoverRequest(DynamicBaseModel):
    record_secrets: bool = False

class DiscoverResponse(BaseAPIResponse):
    status: str
    project_id: int
    thread_id: str

class ProfileContentResponse(BaseAPIResponse):
    content: str | None = None
    exists: bool = False
