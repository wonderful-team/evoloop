"""
Pydantic schemas for context window management.
"""

from langchain_core.messages import BaseMessage
from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class CriticalContext(DynamicBaseModel):
    """Critical context extracted from messages before compaction."""
    decisions: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    current_task: str | None = None


class ContextWindowStats(DynamicBaseModel):
    """Context window manager statistics."""
    max_tokens: int
    compact_threshold: float
    preserve_recent: int


class CompactionResult(DynamicBaseModel):
    """Result of context compaction."""
    messages: list[BaseMessage]
    summary: str
    tokens_saved: int
    original_count: int
    compacted_count: int
