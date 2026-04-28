from enum import Enum

from pydantic import field_validator

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
    error_message: str | None = None

    @property
    def success(self) -> bool:
        return self.status == FileStatus.SUCCESS

    @property
    def has_more(self) -> bool:
        """Check if there's more content (for paginated reads)."""
        return False


class WriteResult(DynamicBaseModel):
    """Result of a file write operation."""
    path: str
    status: FileStatus
    bytes_written: int = 0
    new_hash: str | None = None
    error_message: str | None = None

    @property
    def success(self) -> bool:
        return self.status == FileStatus.SUCCESS


# Convenience type alias
FileMetadata = FileInfo
