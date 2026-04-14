"""
Codebase/Indexing Event Types and Data Structures
==================================================

Event types and data classes for codebase indexing and file watching.
"""

from enum import Enum
from typing import Any

from app.core.events.base import BaseEvent


class IndexingEventType(str, Enum):
    """
    Indexing Domain event types.
    
    Events related to codebase indexing and file watching.
    """
    # Indexing lifecycle events
    INDEXING_STARTED = "indexing.started"
    INDEXING_COMPLETED = "indexing.completed"
    INDEXING_FAILED = "indexing.failed"
    
    # File change events (from watchers)
    FILE_INDEXED = "indexing.file_indexed"
    FILE_REMOVED = "indexing.file_removed"
    FILE_MODIFIED = "indexing.file_modified"  # New: file content changed
    FILE_MOVED = "indexing.file_moved"        # New: file renamed/moved


class CodebaseEvent(BaseEvent):
    """Base class for codebase domain events."""
    source: str = "codebase"


class IndexingStartedEvent(CodebaseEvent):
    """Published when indexing starts for a repository."""
    repo_id: int = 0
    path: str = ""
    
    def model_post_init(self, __context: Any) -> None:
        self.event_type = IndexingEventType.INDEXING_STARTED
        self.data = {
            "repo_id": self.repo_id,
            "path": self.path,
        }


class IndexingCompletedEvent(CodebaseEvent):
    """Published when indexing completes successfully."""
    repo_id: int = 0
    path: str = ""
    file_count: int = 0
    duration_seconds: float = 0.0
    
    def model_post_init(self, __context: Any) -> None:
        self.event_type = IndexingEventType.INDEXING_COMPLETED
        self.data = {
            "repo_id": self.repo_id,
            "path": self.path,
            "file_count": self.file_count,
            "duration_seconds": self.duration_seconds,
        }


class IndexingFailedEvent(CodebaseEvent):
    """Published when indexing fails."""
    repo_id: int = 0
    path: str = ""
    error: str = ""
    
    def model_post_init(self, __context: Any) -> None:
        self.event_type = IndexingEventType.INDEXING_FAILED
        self.data = {
            "repo_id": self.repo_id,
            "path": self.path,
            "error": self.error,
        }


class FileIndexedEvent(CodebaseEvent):
    """Published when a file is indexed."""
    repo_id: int = 0
    file_path: str = ""
    language: str = ""
    
    def model_post_init(self, __context: Any) -> None:
        self.event_type = IndexingEventType.FILE_INDEXED
        self.data = {
            "repo_id": self.repo_id,
            "file_path": self.file_path,
            "language": self.language,
        }


class FileRemovedEvent(CodebaseEvent):
    """Published when a file is removed from index."""
    repo_id: int = 0
    file_path: str = ""
    
    def model_post_init(self, __context: Any) -> None:
        self.event_type = IndexingEventType.FILE_REMOVED
        self.data = {
            "repo_id": self.repo_id,
            "file_path": self.file_path,
        }


class FileModifiedEvent(CodebaseEvent):
    """Published when a file is modified (content changed)."""
    repo_id: int = 0
    file_path: str = ""
    
    def model_post_init(self, __context: Any) -> None:
        self.event_type = IndexingEventType.FILE_MODIFIED
        self.data = {
            "repo_id": self.repo_id,
            "file_path": self.file_path,
        }


class FileMovedEvent(CodebaseEvent):
    """Published when a file is moved/renamed."""
    repo_id: int = 0
    src_path: str = ""
    dest_path: str = ""
    
    def model_post_init(self, __context: Any) -> None:
        self.event_type = IndexingEventType.FILE_MOVED
        self.data = {
            "repo_id": self.repo_id,
            "src_path": self.src_path,
            "dest_path": self.dest_path,
        }


__all__ = [
    # Event types
    "IndexingEventType",
    # Event classes
    "CodebaseEvent",
    "IndexingStartedEvent",
    "IndexingCompletedEvent",
    "IndexingFailedEvent",
    "FileIndexedEvent",
    "FileRemovedEvent",
    "FileModifiedEvent",
    "FileMovedEvent",
]
