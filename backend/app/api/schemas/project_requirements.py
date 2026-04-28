"""API schemas for project_requirements routes."""

from typing import Any

from app.api.schemas.responses import BaseAPIResponse
from app.infrastructure.pydantic_base import DynamicBaseModel


class RequirementUploadResponse(BaseAPIResponse):
    """Response after uploading a requirement document."""
    document_id: str
    thread_id: str
    status: str

class RequirementListItem(DynamicBaseModel):
    """Item in requirement document list."""
    id: str
    file_name: str
    file_type: str
    status: str
    created_at: str | None
    analysis_count: int

class RequirementAnalysisItem(DynamicBaseModel):
    """Analysis item in requirement detail."""
    id: str
    status: str
    version: int
    data: dict[str, Any] | None
    user_edited: bool
    confirmed_at: str | None
    tasks_count: int
    synced_tasks: int

class RequirementDetailResponse(BaseAPIResponse):
    """Response for requirement document detail."""
    id: str
    file_name: str
    file_type: str
    file_size: int
    status: str
    raw_content_preview: str | None
    created_at: str | None
    updated_at: str | None
    analyses: list[RequirementAnalysisItem]

class RequirementDeleteResponse(BaseAPIResponse):
    """Response after deleting a requirement document."""
    status: str
    document_id: str

class RequirementTaskItem(DynamicBaseModel):
    """Task item in requirement task list."""
    id: str
    title: str
    description: str
    priority: str
    estimated_hours: int
    category: str
    tags: list[str]
    requirement_refs: list[str]
    acceptance_criteria: list[str]
    sync_status: str
    sync_error: str | None
    evocloud_task_id: str | None
    synced_at: str | None
    created_at: str | None

class RequirementMapping(DynamicBaseModel):
    """Requirement to task mapping."""
    by_requirement: dict[str, list[str]]
    by_task: dict[str, list[str]]
    unmapped_tasks: list[str]

class RequirementTasksResponse(BaseAPIResponse):
    """Response for analysis tasks."""
    analysis_id: str
    document_id: str
    project_id: int
    sync_stats: dict[str, int]
    tasks: list[RequirementTaskItem]
    requirement_mapping: RequirementMapping

class RequirementProgress(DynamicBaseModel):
    """Sync progress stats."""
    total: int
    synced: int
    failed: int
    syncing: int
    pending: int
    percentage: float
    is_complete: bool
    has_failures: bool

class RequirementSyncProgressResponse(BaseAPIResponse):
    """Response for sync progress."""
    analysis_id: str
    progress: RequirementProgress
    last_updated: str | None
