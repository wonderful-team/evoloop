"""
Codebase Domain Event Definitions and Domain Bus
"""
import logging
from enum import Enum
from typing import Any, Dict

from pydantic import Field

from app.core.events.base import AsyncEventBus
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class IndexingEventType(str, Enum):
    """Event types for the codebase indexing domain."""
    FILE_MODIFIED = "indexing.file_modified"
    FILE_REMOVED = "indexing.file_removed"
    FILE_MOVED = "indexing.file_moved"
    INDEXING_STARTED = "indexing.started"
    INDEXING_COMPLETED = "indexing.completed"
    INDEXING_FAILED = "indexing.failed"


class IndexingEvent(DynamicBaseModel):
    """Generic event for the codebase indexing domain."""
    event_type: IndexingEventType
    repo_id: int
    data: Dict[str, Any] = Field(default_factory=dict)


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


# Codebase domain-specific event bus
# This bus handles file indexing orchestration (Watchers -> Indexers)
event_bus = AsyncEventBus("indexing")
