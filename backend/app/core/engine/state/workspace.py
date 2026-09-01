"""Workspace and clipboard state models."""

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class ClipboardMetadata(DynamicBaseModel):
    source_file: str | None = None
    line_range: tuple[int, int] | None = None


class RetrievalContext(DynamicBaseModel):
    repo_id: int
    files: list[str] = Field(default_factory=list)
    snippets: list[str] = Field(default_factory=list)
