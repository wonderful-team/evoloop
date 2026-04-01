"""
Core file models - Data classes for file operations.

These models are domain-agnostic and can be used by any layer.
"""

from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum


class FileStatus(Enum):
    """Status of a file operation."""
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    ENCODING_ERROR = "encoding_error"
    ERROR = "error"


@dataclass
class FileInfo:
    """Basic file information."""
    path: str
    size: int
    total_lines: int
    encoding: str
    content_hash: str
    is_large: bool = False
    is_binary: bool = False
    exists: bool = True
    
    def __post_init__(self):
        """Ensure hash is truncated for display."""
        if len(self.content_hash) > 16:
            self.content_hash = self.content_hash[:16]


@dataclass
class ReadResult:
    """Result of a file read operation."""
    content: str
    encoding: str
    status: FileStatus
    metadata: FileInfo
    error_message: Optional[str] = None
    
    @property
    def success(self) -> bool:
        return self.status == FileStatus.SUCCESS
    
    @property
    def has_more(self) -> bool:
        """Check if there's more content (for paginated reads)."""
        return self.metadata.total_lines > self.metadata.total_lines


@dataclass
class WriteResult:
    """Result of a file write operation."""
    path: str
    status: FileStatus
    bytes_written: int = 0
    new_hash: Optional[str] = None
    error_message: Optional[str] = None
    
    @property
    def success(self) -> bool:
        return self.status == FileStatus.SUCCESS


@dataclass
class FileChunk:
    """A chunk of file content for streaming."""
    content: str
    line_start: int
    line_end: int
    is_last: bool = False


@dataclass
class PaginationInfo:
    """Pagination metadata."""
    total_lines: int
    start_line: int
    end_line: int
    has_more: bool
    page_size: int = 100


# Convenience type aliases
FileMetadata = FileInfo
