"""API schemas for resources routes."""

from typing import Literal

from app.api.schemas.responses import BaseAPIResponse
from app.infrastructure.pydantic_base import DynamicBaseModel


class ResourceCreate(DynamicBaseModel):
    type: Literal["file", "link"]
    name: str  # user friendly name
    content: str  # Relative Path for file, or URL for link


class ResourceResponse(BaseAPIResponse):
    id: int
    project_id: int
    type: str
    name: str
    content: str
    created_at: str


class OperationResponse(BaseAPIResponse):
    """Simple operation status response."""

    status: str
    id: int
