"""
Metadata models for knowledge extraction.
"""

from datetime import datetime
from typing import Any, Optional, Dict, List

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
