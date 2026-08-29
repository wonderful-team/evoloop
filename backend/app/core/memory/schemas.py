"""Schemas for memory module."""

from datetime import datetime

from pydantic import Field

from app.constants import DEFAULT_PROJECT_ID
from app.infrastructure.pydantic_base import DynamicBaseModel


class StorageHealthCheck(DynamicBaseModel):
    """Health check result for a memory storage backend."""

    status: str = "unknown"
    backend: str = ""
    version: str | None = None
    entry_count: int | None = None
    latency_ms: float | None = None
    error: str | None = None


class MemoryMetadata(DynamicBaseModel):
    source_url: str | None = None
    author: str | None = None
    related_message_ids: list[str] = Field(default_factory=list)


class CheckpointDedupResult(DynamicBaseModel):
    """Result of a checkpoint deduplication operation."""

    dry_run: bool = True
    total_checkpoints: int = 0
    duplicate_groups: int = 0
    duplicates_found: int = 0
    duplicates_removed: int = 0
    bytes_saved: int = 0
    elapsed_ms: int = 0
    error: str | None = None


class Concept(DynamicBaseModel):
    """A semantic concept or knowledge entity extracted from the codebase or conversations."""

    name: str = Field(description="Unique name of the concept, technology, or pattern")
    description: str = Field(
        description="Detailed description of what it is and how it is used"
    )
    project_id: int | None = Field(
        default=DEFAULT_PROJECT_ID,
        description="Associated project ID (DEFAULT_PROJECT_ID/0 for global)",
    )
    related_files: list[str] = Field(
        default_factory=list, description="List of file paths related to this concept"
    )
    source_thread_id: str | None = Field(
        default=None, description="Thread ID where this concept was discovered"
    )
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Episode(DynamicBaseModel):
    """A recorded execution episode representing a past task attempt."""

    id: str | None = None
    goal: str = Field(description="What was the agent trying to achieve")
    result: str = Field(description="The outcome of the attempt")
    plan_summary: str | None = Field(
        default=None, description="Summary of the plan used"
    )
    error_msg: str | None = Field(default=None, description="Error message if failed")
    project_id: int | None = Field(default=DEFAULT_PROJECT_ID)
    source_message_id: str | None = Field(default=None)
    member_id: int | None = Field(default=None)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RetrievalContext(DynamicBaseModel):
    """Context for memory retrieval."""

    query: str
    recent_tools: list[str] = Field(default_factory=list)
    already_surfaced: set[str] = Field(
        default_factory=set
    )  # Memory IDs already shown to user
    member_id: int | None = None
    project_id: int | None = None


class ForgottenRecord(DynamicBaseModel):
    """Record of a forgotten tool output."""

    tool_call_id: str
    tool_name: str
    summary: str
    original_length: int
    forgotten_at: float
    reason: str
    step_index: int  # The message index when it was forgotten


class AuditEntry(DynamicBaseModel):
    """Audit log entry for tracking forget/recall operations."""

    action: str  # "forget" or "recall"
    tool_call_id: str
    timestamp: float
    reason: str
    success: bool
    details: str = ""


class MemorySectionEntry(DynamicBaseModel):
    """A single entry in a MEMORY.md section."""

    id: str | None = None
    title: str
    description: str
    score: float | None = None
    type: str | None = None
