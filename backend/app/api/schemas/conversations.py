"""API schemas for conversations routes."""

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.api.schemas.responses import BaseAPIResponse, ListResponse
from app.core.engine.state.history import FoldedMessage
from datetime import datetime
from typing import Any, Optional

class MessageItem(FoldedMessage):
    run_id: str | None = None
    parent_id: int | None = None
    references: list["ReferenceItem"] = []
    has_file_operations: bool = False
    changeset_count: int = 0
    category: str | None = None
    content_type: str = "text"
    status: str | None = None
    sequence_number: int | None = None
    checkpoint_id: str | None = None
    is_visible: bool = True
    thinking: str | list[dict[str, Any]] | None = None
    tool_blocks: list[dict[str, Any]] | None = None

class ConversationSearchResult(DynamicBaseModel):
    id: int  # Message ID
    thread_id: str
    role: str
    content: str
    created_at: str
    match_snippet: str | None = None

class RenameRequest(DynamicBaseModel):
    title: str

class ConversationListItem(DynamicBaseModel):
    thread_id: str
    title: str
    project_id: int | None
    updated_at: datetime | None
    status: str = "idle"

class ReferenceItemMetadata(DynamicBaseModel):
    """Metadata for a message reference. Extra fields allowed per reference type."""
    duration: float | None = None
    transcript: str | None = None
    waveform: list[float] | None = None
    url: str | None = None
    mime_type: str | None = None

class ReferenceItem(DynamicBaseModel):
    id: str
    type: str
    target_id: str
    target_name: str
    metadata: ReferenceItemMetadata | None = None  # Additional metadata (duration, transcript, waveform, etc.)

class ChangesetNode(DynamicBaseModel):
    """Hierarchical node for file operation tree."""
    name: str
    path: str
    is_dir: bool
    operation: str | None = None  # ADD, EDIT, DELETE
    diff: str | None = None
    children: list["ChangesetNode"] = []

class RewindResponse(BaseAPIResponse):
    status: str
    thread_id: str
    removed_count: int = 0
    files_reverted: int = 0

class ConversationRenameResponse(BaseAPIResponse):
    status: str
    thread_id: str
    title: str

class ConversationDeleteResponse(BaseAPIResponse):
    status: str
    thread_id: str

class RewindRequest(DynamicBaseModel):
    revert_files: bool = True  # Whether to also revert file changes
    message_id: str | None = None  # Optional: target message to rewind to

class MessageListResponse(ListResponse[MessageItem]):
    """Response model for paginated message list."""
    has_more: bool
    first_id: int | None = None
    last_id: int | None = None
    total_count: int | None = None
