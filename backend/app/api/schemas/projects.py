"""API schemas for projects routes."""

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.api.schemas.responses import BaseAPIResponse, ListResponse
from app.models.schemas.base import ScopedRequest
from typing import Any, Optional

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
    """System task activity state."""
    status: str = "idle"
    updated_at: float = 0.0
    agent_state: dict = {}
    steps: list = []

class ProjectStatusResponse(BaseAPIResponse):
    """Real-time project system status."""
    indexing: ProjectStatusActivity
    summarization: ProjectStatusActivity
    wiki: ProjectStatusActivity

class ProjectDeleteResponse(BaseAPIResponse):
    """Project deletion response."""
    status: str
    id: int

class IndexingRunResponse(BaseAPIResponse):
    """Indexing dispatch response."""
    status: str
    project_id: int

class DetectedProjectItem(DynamicBaseModel):
    """Detected project awaiting import."""
    id: int
    name: str
    path: str | None
    detected_at: str | None

class ImportProjectResponse(BaseAPIResponse):
    """Project import response."""
    status: str
    repo_id: int
    name: str

class IgnoreProjectResponse(BaseAPIResponse):
    """Project ignore response."""
    status: str
    repo_id: int

class UnignoreProjectResponse(BaseAPIResponse):
    """Project unignore response."""
    status: str
    repo_id: int
    name: str

class BatchResultItem(DynamicBaseModel):
    """Single result in batch operation."""
    repo_id: int
    name: str | None = None
    error: str | None = None

class BatchImportResponse(BaseAPIResponse):
    """Batch import response."""
    status: str
    summary: str
    results: dict[str, list[BatchResultItem]]

class BatchImportRequest(DynamicBaseModel):
    repo_ids: list[int]
