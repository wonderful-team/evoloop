"""API schemas for memory routes."""

from typing import Any

from app.api.schemas.responses import BaseAPIResponse, ListResponse
from app.infrastructure.pydantic_base import DynamicBaseModel


class ConceptCreate(DynamicBaseModel):
    name: str
    description: str
    related_files: list[str] | None = None
    source_message_id: str | None = None
    source_thread_id: str | None = None


class ConceptUpdate(DynamicBaseModel):
    description: str | None = None
    related_files: list[str] | None = None


class ConceptResponse(BaseAPIResponse):
    name: str
    description: str | None = None
    episode_count: int | None = 0


class EpisodeResponse(BaseAPIResponse):
    id: str
    goal: str
    result: str | None
    error: str | None
    timestamp: str | None  # ISO format datetime string from Neo4j


class VectorSearchResult(DynamicBaseModel):
    """Vector search result item."""

    id: str
    content: str
    file_path: str
    repository_id: str
    chunk_type: str
    identifier: str
    start_line: int
    end_line: int
    language: str
    score: float


class VectorSearchResponse(ListResponse[VectorSearchResult]):
    """Vector search response."""

    query: str
    search_type: str


class HybridResultItem(DynamicBaseModel):
    """Single item in hybrid search results."""

    type: str
    score: float
    data: dict[str, Any]


class HybridSearchResponse(ListResponse[HybridResultItem]):
    """Hybrid search response."""

    query: str
    search_type: str
    vector_results_count: int | None = None
    text_results_count: int | None = None


class ConceptOperationResponse(BaseAPIResponse):
    """Response for concept add/delete/update operations."""

    status: str
    name: str
