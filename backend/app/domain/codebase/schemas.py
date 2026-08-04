"""Schemas for codebase module."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.codebase import Repository, SourceFile
from app.models.schemas.document import Document


class ExtractedEntity(DynamicBaseModel):
    name: str
    type: str
    full_name: str
    start_line: int
    end_line: int
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractedRelation(DynamicBaseModel):
    source_full_name: str
    target_full_name: str
    relation_type: str
    start_line: int | None = None


class ExtractionResult(DynamicBaseModel):
    documents: list[Document] = Field(default_factory=list)
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)


class IndexedContent(BaseModel):
    """Result of content indexing, ready for persistence."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    documents: list[Document]
    entities: list[ExtractedEntity]
    relations: list[ExtractedRelation]
    embeddings: list[list[float]]
    file_summary_doc: Document  # Whole file summary chunk


class PreparedFile(BaseModel):
    """Result of file preparation, ready for indexing."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    file_path: str
    rel_path: str
    content: str
    checksum: str
    source_file: SourceFile | None
    is_new: bool
    repo: Repository


class APIEndpoint(DynamicBaseModel):
    method: str
    path: str
    handler_name: str
    file_path: str
    line_number: int


class DBTable(DynamicBaseModel):
    name: str
    file_path: str
    columns: list[str] = Field(default_factory=list)
