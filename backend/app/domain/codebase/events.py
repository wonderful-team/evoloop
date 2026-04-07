"""
Codebase/Indexing Event Types and Data Structures
==================================================

Event types and data classes for codebase indexing and file watching.
"""

from dataclasses import dataclass, field
from datetime import datetime
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


@dataclass
class CodebaseEvent(BaseEvent):
    """Base class for codebase domain events."""
    source: str = "codebase"


@dataclass
class IndexingStartedEvent(CodebaseEvent):
    """Published when indexing starts for a repository."""
    repo_id: int = 0
    path: str = ""
    
    def __post_init__(self):
        self.event_type = IndexingEventType.INDEXING_STARTED
        self.data = {
            "repo_id": self.repo_id,
            "path": self.path,
        }


@dataclass
class IndexingCompletedEvent(CodebaseEvent):
    """Published when indexing completes successfully."""
    repo_id: int = 0
    path: str = ""
    file_count: int = 0
    duration_seconds: float = 0.0
    
    def __post_init__(self):
        self.event_type = IndexingEventType.INDEXING_COMPLETED
        self.data = {
            "repo_id": self.repo_id,
            "path": self.path,
            "file_count": self.file_count,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class IndexingFailedEvent(CodebaseEvent):
    """Published when indexing fails."""
    repo_id: int = 0
    path: str = ""
    error: str = ""
    
    def __post_init__(self):
        self.event_type = IndexingEventType.INDEXING_FAILED
        self.data = {
            "repo_id": self.repo_id,
            "path": self.path,
            "error": self.error,
        }


@dataclass
class FileIndexedEvent(CodebaseEvent):
    """Published when a file is indexed."""
    repo_id: int = 0
    file_path: str = ""
    language: str = ""
    
    def __post_init__(self):
        self.event_type = IndexingEventType.FILE_INDEXED
        self.data = {
            "repo_id": self.repo_id,
            "file_path": self.file_path,
            "language": self.language,
        }


@dataclass
class FileRemovedEvent(CodebaseEvent):
    """Published when a file is removed from index."""
    repo_id: int = 0
    file_path: str = ""
    
    def __post_init__(self):
        self.event_type = IndexingEventType.FILE_REMOVED
        self.data = {
            "repo_id": self.repo_id,
            "file_path": self.file_path,
        }


@dataclass
class FileModifiedEvent(CodebaseEvent):
    """Published when a file is modified (content changed)."""
    repo_id: int = 0
    file_path: str = ""
    
    def __post_init__(self):
        self.event_type = IndexingEventType.FILE_MODIFIED
        self.data = {
            "repo_id": self.repo_id,
            "file_path": self.file_path,
        }


@dataclass
class FileMovedEvent(CodebaseEvent):
    """Published when a file is moved/renamed."""
    repo_id: int = 0
    src_path: str = ""
    dest_path: str = ""
    
    def __post_init__(self):
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
