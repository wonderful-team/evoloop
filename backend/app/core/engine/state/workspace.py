"""Workspace and clipboard state models."""
import time
from typing import Any, List, Optional

from pydantic import Field
from app.infrastructure.pydantic_base import DynamicBaseModel


class ClipboardMetadata(DynamicBaseModel):
    source_file: Optional[str] = None
    line_range: Optional[tuple[int, int]] = None


class SubtaskContext(DynamicBaseModel):
    description: Optional[str] = None
    dependencies: Optional[List[str]] = None


class ClipboardItem(DynamicBaseModel):
    content: Any
    mime_type: str
    metadata: ClipboardMetadata = Field(default_factory=ClipboardMetadata)
    created_at: float = Field(default_factory=time.time)


class WorkspaceContext(DynamicBaseModel):
    structure: Optional[str] = None
    structure_updated_at: Optional[float] = None


class RetrievalContext(DynamicBaseModel):
    repo_id: int
    files: List[str] = Field(default_factory=list)
    snippets: List[str] = Field(default_factory=list)
