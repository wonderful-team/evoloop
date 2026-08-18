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
    """Structured project settings stored in .evoloop/project.json.

    值守配置（customer_service_duty）已拆分到独立端点 PUT /projects/{id}/duty
    （v7），settings 不再承载。
    """

    name: str | None = None
    url: str | None = None


class ProfileContentResponse(BaseAPIResponse):
    content: str | None = None
    exists: bool = False
    url: str | None = None
    name: str | None = None
    framework_profile: dict | None = None


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
