"""Schemas for file module."""

from enum import Enum

from app.infrastructure.pydantic_base import DynamicBaseModel


class DirectoryStatus(Enum):
    """Status of a directory operation."""

    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ALREADY_EXISTS = "already_exists"
    PERMISSION_DENIED = "permission_denied"
    NOT_EMPTY = "not_empty"
    ERROR = "error"


class DirectoryInfo(DynamicBaseModel):
    """Information about a directory."""

    path: str
    exists: bool
    is_empty: bool = False
    file_count: int = 0
    subdir_count: int = 0
    total_size: int = 0


class DirectoryOperationResult(DynamicBaseModel):
    """Result of a directory operation."""

    success: bool
    status: DirectoryStatus
    path: str
    message: str = ""
    destination: str | None = None  # For move operations


class DirectoryEntry(DynamicBaseModel):
    """A single entry in directory listing."""

    name: str
    path: str
    is_dir: bool
    size: int = 0


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


class FileStats(DynamicBaseModel):
    """File statistics for a preview."""

    path: str
    size: int
    total_lines: int
    encoding: str | None = None
    content_hash: str | None = None


class OutlineEntry(DynamicBaseModel):
    """A single entry in file outline."""

    type: str  # 'class', 'function', 'method', 'variable', etc.
    name: str
    line: int  # 1-based line number
    indent: int  # indentation level in spaces


class FilePreview(DynamicBaseModel):
    stats: FileStats
    outline: list[OutlineEntry]
    preview: str
    preview_lines: list[int]


class FileWriteResult(DynamicBaseModel):
    success: bool
    path: str | None = None
    new_hash: str | None = None
    current_hash: str | None = None
    bytes_written: int | None = None
    error: str | None = None
    message: str | None = None
    change_count: int | None = None
