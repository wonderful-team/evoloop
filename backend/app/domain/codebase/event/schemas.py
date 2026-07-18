"""
Codebase Indexing Event Schemas
===============================

Pydantic data classes for codebase indexing events.
"""

from typing import Any

from pydantic import Field

from app.core.events.base import BaseEvent
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


class IndexingStatusChangedEvent(BaseEvent):
    """
    Public event triggered when a project's indexing status changes.
    Bridged to the frontend via UniversalBridgeSubscriber.
    """
    event_type: str = IndexingEventType.INDEXING_STATUS_CHANGED
    source: str = "indexing"
    project_id: int
    repo_id: int | None = None
    status: str
    is_public: bool = True
    broadcast_channel: str = "system"

    def model_post_init(self, __context: Any) -> None:
        self.data = {
            "project_id": self.project_id,
            "repo_id": self.repo_id,
            "status": self.status,
        }


class IndexingCompletedEvent(BaseEvent):
    """
    Event triggered when a project's full indexing completes successfully.
    Subscribers can use this to trigger downstream tasks (wiki, appmap, summary).
    """
    event_type: str = IndexingEventType.INDEXING_COMPLETED
    source: str = "indexing"
    project_id: int
    repo_id: int
    is_public: bool = False

    def model_post_init(self, __context: Any) -> None:
        self.data = {
            "project_id": self.project_id,
            "repo_id": self.repo_id,
        }


class GenerationStatusChangedEvent(BaseEvent):
    """
    Public event triggered when a generation artifact status changes.
    Bridged to the frontend via UniversalBridgeSubscriber.
    """
    event_type: str = IndexingEventType.GENERATION_STATUS_CHANGED
    source: str = "generation"
    project_id: int
    item: str
    status: str
    error: str | None = None
    is_public: bool = True
    broadcast_channel: str = "system"

    def model_post_init(self, __context: Any) -> None:
        self.data = {
            "project_id": self.project_id,
            "item": self.item,
            "status": self.status,
            "error": self.error,
        }
