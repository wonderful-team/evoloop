"""API schemas for projects routes."""

from pydantic import Field

from app.api.schemas.responses import BaseAPIResponse
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.schemas.base import ScopedRequest

# Re-export from sub-modules so `from app.api.schemas.projects import *` covers everything
from .modules import *  # noqa: F401,F403
from .profiles import *  # noqa: F401,F403


class IndexingRequest(ScopedRequest):
    project_id: int


class CreateProjectRequest(DynamicBaseModel):
    name: str
    description: str = ""
    path: str | None = None
    sub_path: str | None = None


class ImportProjectByPathRequest(DynamicBaseModel):
    path: str
    name: str | None = None


class ImportProjectByPathResponse(BaseAPIResponse):
    status: str
    repo_id: int
    project_id: int | None = None
    name: str


class UpdateProjectRequest(DynamicBaseModel):
    name: str | None = None
    description: str | None = None
    path: str | None = None


class ProjectStatusActivity(DynamicBaseModel):
    status: str = "idle"
    updated_at: float = 0.0
    agent_state: dict = {}
    steps: list = []


class ProjectStatusResponse(BaseAPIResponse):
    indexing: ProjectStatusActivity
    summarization: ProjectStatusActivity
    wiki: ProjectStatusActivity


class ProjectDeleteResponse(BaseAPIResponse):
    status: str
    id: int


class IndexingRunResponse(BaseAPIResponse):
    status: str
    project_id: int


class GenerationItemRequest(DynamicBaseModel):
    project_id: int
    artifact_names: list[str] = Field(alias="items")


class GenerationRetryRequest(DynamicBaseModel):
    project_id: int
    artifact_name: str = Field(alias="item")


class GenerationStatusRecord(DynamicBaseModel):
    item: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    error: str | None = None


class GenerationDispatchResponse(BaseAPIResponse):
    project_id: int
    dispatched: list[str]
    records: dict[str, GenerationStatusRecord] = Field(alias="items")


class GenerationStatusResponse(BaseAPIResponse):
    project_id: int
    records: list[GenerationStatusRecord] = Field(alias="items")


class GenerationContentResponse(BaseAPIResponse):
    project_id: int
    item: str
    content: str | None = None
    content_type: str = "markdown"


__all__ = [
    "IndexingRequest",
    "CreateProjectRequest",
    "ImportProjectByPathRequest",
    "ImportProjectByPathResponse",
    "UpdateProjectRequest",
    "ProjectStatusActivity",
    "ProjectStatusResponse",
    "ProjectDeleteResponse",
    "IndexingRunResponse",
    "GenerationItemRequest",
    "GenerationRetryRequest",
    "GenerationStatusRecord",
    "GenerationDispatchResponse",
    "GenerationStatusResponse",
    "GenerationContentResponse",
]
