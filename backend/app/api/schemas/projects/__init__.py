"""API schemas for projects routes."""

from app.api.schemas.responses import BaseAPIResponse
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.schemas.base import ScopedRequest

# Re-export from sub-modules so `from app.api.schemas.projects import *` covers everything
from ._modules import *  # noqa: F401,F403
from ._profiles import *  # noqa: F401,F403


class IndexingRequest(ScopedRequest):
    project_id: int

class CreateProjectRequest(DynamicBaseModel):
    name: str
    description: str = ""
    path: str

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

class DetectedProjectItem(DynamicBaseModel):
    id: int
    name: str
    path: str | None
    detected_at: str | None

class ImportProjectResponse(BaseAPIResponse):
    status: str
    repo_id: int
    name: str

class IgnoreProjectResponse(BaseAPIResponse):
    status: str
    repo_id: int

class UnignoreProjectResponse(BaseAPIResponse):
    status: str
    repo_id: int
    name: str

class BatchResultItem(DynamicBaseModel):
    repo_id: int
    name: str | None = None
    error: str | None = None

class BatchImportResponse(BaseAPIResponse):
    status: str
    summary: str
    results: dict[str, list[BatchResultItem]]

class BatchImportRequest(DynamicBaseModel):
    repo_ids: list[int]


__all__ = [
    "IndexingRequest",
    "CreateProjectRequest",
    "UpdateProjectRequest",
    "ProjectStatusActivity",
    "ProjectStatusResponse",
    "ProjectDeleteResponse",
    "IndexingRunResponse",
    "DetectedProjectItem",
    "ImportProjectResponse",
    "IgnoreProjectResponse",
    "UnignoreProjectResponse",
    "BatchResultItem",
    "BatchImportResponse",
    "BatchImportRequest",
]
