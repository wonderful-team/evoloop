"""API schemas for files routes."""

from app.api.schemas.responses import BaseAPIResponse
from app.infrastructure.pydantic_base import DynamicBaseModel


class FileNode(DynamicBaseModel):
    name: str  # display name
    path: str  # relative path to project root
    type: str  # 'file' or 'directory'
    children: list["FileNode"] | None = None

class FileContent(DynamicBaseModel):
    content: str
    language: str

class OpenFileRequest(DynamicBaseModel):
    path: str

class OpenFileResponse(BaseAPIResponse):
    """Response for opening a file."""
    status: str

class FileUploadResponse(BaseAPIResponse):
    """Response for uploading a file."""
    url: str
    filename: str
    path: str

class FileSearchResult(DynamicBaseModel):
    """Single file content search result."""
    file: str
    line: int
    content: str

class FileNameSearchResult(DynamicBaseModel):
    """Single file name search result."""
    name: str
    path: str
    type: str

class CreateFileRequest(DynamicBaseModel):
    path: str
    content: str

class MkdirRequest(DynamicBaseModel):
    path: str

class MoveFileRequest(DynamicBaseModel):
    source_path: str
    target_path: str
