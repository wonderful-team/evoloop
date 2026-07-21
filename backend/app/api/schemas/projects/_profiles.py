"""API schemas for project profile discovery routes."""

from app.api.schemas.responses import BaseAPIResponse
from app.infrastructure.pydantic_base import DynamicBaseModel


class DiscoverRequest(DynamicBaseModel):
    record_secrets: bool = False


class DiscoverResponse(BaseAPIResponse):
    status: str
    project_id: int
    thread_id: str


class ProjectSettings(DynamicBaseModel):
    """Structured project settings stored in .evoloop/project.json."""

    name: str | None = None
    url: str | None = None


class ProfileContentResponse(BaseAPIResponse):
    content: str | None = None
    exists: bool = False
    url: str | None = None
    name: str | None = None


class UpdateProfileRequest(DynamicBaseModel):
    content: str
    name: str | None = None
    url: str | None = None


__all__ = [
    "DiscoverRequest",
    "DiscoverResponse",
    "ProfileContentResponse",
    "UpdateProfileRequest",
    "ProjectSettings",
]
