"""Workspace and clipboard state models."""
import time
from typing import Any

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class ClipboardMetadata(DynamicBaseModel):
    source_file: str | None = None
    line_range: tuple[int, int] | None = None


class ClipboardItem(DynamicBaseModel):
    content: Any
    mime_type: str
    metadata: ClipboardMetadata = Field(default_factory=ClipboardMetadata)
    created_at: float = Field(default_factory=time.time)


class WorkspaceContext(DynamicBaseModel):
    structure: str | None = None
    structure_updated_at: float | None = None


class RetrievalContext(DynamicBaseModel):
    repo_id: int
    files: list[str] = Field(default_factory=list)
    snippets: list[str] = Field(default_factory=list)
