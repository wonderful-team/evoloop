"""Schemas for knowledge module."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class ExtractorInfo(DynamicBaseModel):
    """Information about the extractor used."""
    name: str
    version: str = "1.0"
    config: Dict[str, Any] = Field(default_factory=dict)


class DocumentMetadata(DynamicBaseModel):
    """
    Rich metadata for extracted documents.
    
    This is stored alongside the Markdown content in the meta/ directory.
    """
    # Basic info
    source_file: str
    source_mime_type: str
    file_size_bytes: int

    # Extraction info
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    extractor: ExtractorInfo = Field(default_factory=lambda: ExtractorInfo(name="unknown"))
    extraction_duration_ms: Optional[float] = None

    # Content analysis (populated by extractors)
    title: Optional[str] = None
    author: Optional[str] = None
    language: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    summary: Optional[str] = None

    # Structure info
    page_count: Optional[int] = None
    section_count: Optional[int] = None
    code_block_count: Optional[int] = None
    table_count: Optional[int] = None

    # Links and references
    links: List[str] = Field(default_factory=list)
    images: List[str] = Field(default_factory=list)

    # Quality metrics
    ocr_confidence: Optional[float] = None
    extraction_quality: Optional[str] = None  # 'high', 'medium', 'low'

    # Chunking info (for large documents)
    is_chunked: bool = False
    total_chunks: int = 1
    chunk_index: int = 0

    # Custom metadata from specific extractors
    custom: Dict[str, Any] = Field(default_factory=dict)


class MaintenanceConfig(BaseModel):
    """Configuration for auto-maintenance tasks."""
    enable_auto_merge: bool = True
    enable_auto_archive: bool = True
    similarity_threshold: float = 0.85
    cold_doc_days: int = 90
    min_quality_score: float = 0.3


class UsageDocInfo(DynamicBaseModel):
    """Usage information for a single document."""
    path: str
    citations: int
    last_accessed: Optional[str] = None
    unique_sessions: Optional[int] = None


class UsageAnalysisResult(DynamicBaseModel):
    """Result of analyzing document usage patterns."""
    hot_docs: list[UsageDocInfo] = Field(default_factory=list)
    cold_docs: list[UsageDocInfo] = Field(default_factory=list)
    total_analyzed: int = 0


class OptimizationSuggestion(DynamicBaseModel):
    """Optimization suggestion based on usage analysis."""
    type: str
    reason: str
    priority: str = "medium"
    path: Optional[str] = None
    count: Optional[int] = None


class DocumentQuality(DynamicBaseModel):
    """文档质量评估"""
    path: str
    score: float  # 0.0 - 1.0
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class TaggingResult(DynamicBaseModel):
    """Result of auto-tagging."""
    tags: list[str] = Field(default_factory=list)
    category: str  # primary category
    confidence: float
    summary: str  # brief summary of document
    keywords: list[str] = Field(default_factory=list)  # extracted keywords


class BulkImportError(DynamicBaseModel):
    """Error entry for a bulk import operation."""
    file: str
    error: str


class ArchiveValidationResult(DynamicBaseModel):
    """Result of archive validation."""
    valid: bool
    total_files: int = 0
    processable_files: int = 0
    total_size_bytes: int = 0
    compressed_size_bytes: int = 0
    sample_files: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class DocumentStats(DynamicBaseModel):
    """Citation statistics for a document."""

    doc_id: str
    doc_path: str
    total_citations: int = 0
    unique_sessions: int = 0
    last_accessed: Optional[datetime] = None
    tools_used: dict[str, int] = {}
    related_docs: list[str] = []


class DocumentRecommendation(DynamicBaseModel):
    """Document recommendation based on citation patterns."""

    path: str
    reason: str
    relevance: float
    total_citations: int


class DuplicateResult(DynamicBaseModel):
    """Result of duplicate detection."""
    doc_id: str
    path: str
    similarity: float  # 0.0 to 1.0
    match_type: str  # "exact", "content", "title", "fuzzy"
    suggested_action: str  # "keep", "merge", "delete"


class MergeSuggestion(DynamicBaseModel):
    """Suggested document merge."""
    documents: list[str]
    suggested_title: str
    strategy: str  # "concatenate", "diff", "selective"


class MergeResult(DynamicBaseModel):
    """Result of merging documents."""
    success: bool
    path: Optional[str] = None
    source_count: Optional[int] = None
    strategy: Optional[str] = None
    error: Optional[str] = None


class DeleteDuplicatesResult(DynamicBaseModel):
    """Result of deleting duplicate documents."""
    deleted: int
    errors: list[dict] = Field(default_factory=list)


class DocumentSaveResult(DynamicBaseModel):
    """Result of saving a document to the knowledge base."""
    path: str
    title: str
    content: str
    collection: str
    size: int
    word_count: int
    source_project_id: Optional[int] = None


class DocumentReadResult(DynamicBaseModel):
    """Result of reading a document from the knowledge base."""
    content: str
    frontmatter: dict
    extracted_metadata: Optional[dict] = None
    path: str
    encoding: str
    offset: int
    limit: Optional[int] = None
    total_lines: int
    has_more: bool
    content_hash: Optional[str] = None


class DocumentListItem(DynamicBaseModel):
    """Item in a document list from the knowledge base."""
    path: str
    size_bytes: int
    modified_at: str
    has_metadata: bool
    tags: list[str]
    title: str
    source: Optional[str] = None
    source_project_id: Optional[int] = None


class KBReadInput(BaseModel):
    """Input for kb_read tool."""
    path: str = Field(
        description="Path to the document (e.g., 'guides/auth.md' or 'collection/api/guide.md')"
    )
    offset: int = Field(
        default=0,
        description="Line offset to start reading from (0-based)"
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of lines to read (max 500)"
    )
    collection: str = Field(
        default="",
        description="Collection name (if not included in path)"
    )


# ============== Harvesting Schemas ==============

class ExtractedKnowledge(BaseModel):
    """A single piece of knowledge extracted from conversation."""
    title: str = Field(..., description="Short descriptive title of the knowledge")
    content: str = Field(..., description="The actual knowledge content, formatted as Markdown")
    category: str = Field(..., description="Category, e.g., 'technical_rule', 'business_logic', 'workflow', 'environment'")
    tags: list[str] = Field(default_factory=list, description="Relevant tags")
    confidence: float = Field(..., ge=0.0, le=1.0, description="How certain we are that this is valuable knowledge")
    source_context: str | None = Field(None, description="Excerpt from conversation for tracing")


class KnowledgeHarvestingResult(BaseModel):
    """The full result of a knowledge extraction run."""
    items: list[ExtractedKnowledge] = Field(default_factory=list)
    summary: str = Field(default="", description="Brief summary of the knowledge discovered")
