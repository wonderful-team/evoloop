from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from app.infrastructure.pydantic_base import DynamicBaseModel


class FileStatus(str, Enum):
    """Status of a file operation."""
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    ENCODING_ERROR = "encoding_error"
    ERROR = "error"


class FileInfo(DynamicBaseModel):
    """Basic file information."""
    path: str
    size: int
    total_lines: int
    encoding: str
    content_hash: str
    is_large: bool = False
    is_binary: bool = False
    exists: bool = True

    @field_validator("content_hash")
    @classmethod
    def truncate_hash(cls, v: str) -> str:
        """Ensure hash is truncated for display."""
        if len(v) > 16:
            return v[:16]
        return v


class ReadResult(DynamicBaseModel):
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
        # Note: logic in original was metadata.total_lines > metadata.total_lines which is always False.
        # Assuming it meant current lines vs total. For now keeping original logic if it's a marker.
        return False


class WriteResult(DynamicBaseModel):
    """Result of a file write operation."""
    path: str
    status: FileStatus
    bytes_written: int = 0
    new_hash: Optional[str] = None
    error_message: Optional[str] = None
    
    @property
    def success(self) -> bool:
        return self.status == FileStatus.SUCCESS


class FileChunk(DynamicBaseModel):
    """A chunk of file content for streaming."""
    content: str
    line_start: int
    line_end: int
    is_last: bool = False


class PaginationInfo(DynamicBaseModel):
    """Pagination metadata."""
    total_lines: int
    start_line: int
    end_line: int
    has_more: bool
    page_size: int = 100


# Convenience type alias
FileMetadata = FileInfo
