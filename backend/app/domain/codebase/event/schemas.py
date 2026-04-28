"""
Codebase Indexing Event Schemas
===============================

Pydantic data classes for codebase indexing events.
"""

from typing import Any

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel
from .types import IndexingEventType


class IndexingEvent(DynamicBaseModel):
    """Generic event for the codebase indexing domain."""
    event_type: IndexingEventType
    repo_id: int
    data: dict[str, Any] = Field(default_factory=dict)


class FileModifiedEvent(DynamicBaseModel):
    """Triggered when a code file is created or modified."""
    event_type: IndexingEventType = IndexingEventType.FILE_MODIFIED
    repo_id: int
    file_path: str


class FileRemovedEvent(DynamicBaseModel):
    """Triggered when a code file is deleted."""
    event_type: IndexingEventType = IndexingEventType.FILE_REMOVED
    repo_id: int
    file_path: str


class FileMovedEvent(DynamicBaseModel):
    """Triggered when a code file is moved or renamed."""
    event_type: IndexingEventType = IndexingEventType.FILE_MOVED
    repo_id: int
    src_path: str
    dest_path: str
