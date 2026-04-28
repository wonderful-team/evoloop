"""API schemas for knowledge routes."""

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.infrastructure.schemas import SearchResults
from app.api.schemas.responses import BaseAPIResponse, ListResponse
from app.domain.knowledge.services.store import DocumentListItem
from typing import Any, Optional

class DocumentResponse(BaseAPIResponse):
    """Response for document operations."""
    path: Optional[str] = None
    document: Optional[dict] = None

class DocumentListResponse(ListResponse[DocumentListItem]):
    """Response for listing documents."""
    documents: list[DocumentListItem]
    collections: list[str]

class DocumentMetadataResponse(BaseAPIResponse):
    """Structured metadata for a document chunk/response."""
    title: str | None = None
    source_file: str | None = None
    source_mime_type: str | None = None
    file_size_bytes: int | None = None
    extracted_at: str | None = None
    source_project_id: int | None = None

class DocumentContentResponse(BaseAPIResponse):
    """Response for reading document content."""
    path: str
    content: str
    metadata: DocumentMetadataResponse
    offset: int
    limit: int
    total_lines: int
    has_more: bool

class CollectionResponse(BaseAPIResponse):
    """Response for listing collections."""
    collections: list[str]
    stats: dict[str, Any]

class TagItem(DynamicBaseModel):
    """Single tag with document count."""
    name: str
    count: int

class TagResponse(BaseAPIResponse):
    """Response for listing tags."""
    tags: list[TagItem]
    total: int

class DocumentSearchItem(DynamicBaseModel):
    """Single document search result."""
    path: str
    match_count: int
    matches: list[dict[str, Any]]

class FTSSearchResult(DynamicBaseModel):
    """Single FTS search result."""
    doc_id: str
    path: str
    collection: str | None
    title: str
    snippet: str
    highlights: str
    score: float

class DocumentSearchResponse(SearchResults):
    """Response for document search."""
    results: list[DocumentSearchItem]

class FTSSearchResponse(SearchResults):
    """Response for FTS search."""
    results: list[FTSSearchResult]
    facets: dict[str, Any]

class FTSSuggestResponse(BaseAPIResponse):
    """Response for FTS suggestions."""
    suggestions: list[str]
