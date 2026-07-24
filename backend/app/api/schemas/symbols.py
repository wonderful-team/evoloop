"""API schemas for symbols routes."""

from app.api.schemas.responses import BaseAPIResponse


class SymbolResponse(BaseAPIResponse):
    """Code symbol search result."""
    id: int
    name: str
    full_name: str
    type: str
    file_path: str
    start_line: int
    end_line: int

class SymbolWikiResponse(BaseAPIResponse):
    """Response for symbol wiki generation."""
    content: str

class SymbolRelationResponse(BaseAPIResponse):
    """Dependency relationship between code entities/files."""
    id: int
    source_id: int
    target_id: int | None = None
    source_name: str
    target_name: str | None = None
    relation_type: str
    source_file_path: str
    target_file_path: str | None = None
