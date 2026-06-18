"""
Codebase Indexing Event Types
=============================

Event type constants for codebase indexing domain.
"""

from enum import Enum


class IndexingEventType(str, Enum):
    """Event types for the codebase indexing domain."""
    FILE_MODIFIED = "indexing.file_modified"
    FILE_REMOVED = "indexing.file_removed"
    FILE_MOVED = "indexing.file_moved"
    INDEXING_STARTED = "indexing.started"
    INDEXING_COMPLETED = "indexing.completed"
    INDEXING_FAILED = "indexing.failed"
    INDEXING_STATUS_CHANGED = "indexing.status"
