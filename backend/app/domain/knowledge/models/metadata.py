"""
Metadata models for knowledge extraction.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ExtractorInfo:
    """Information about the extractor used."""
    name: str
    version: str = "1.0"
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentMetadata:
    """
    Rich metadata for extracted documents.
    
    This is stored alongside the Markdown content in the meta/ directory.
    """
    # Basic info
    source_file: str
    source_mime_type: str
    file_size_bytes: int
    
    # Extraction info
    extracted_at: datetime = field(default_factory=datetime.utcnow)
    extractor: ExtractorInfo = field(default_factory=lambda: ExtractorInfo("unknown"))
    extraction_duration_ms: Optional[float] = None
    
    # Content analysis (populated by extractors)
    title: Optional[str] = None
    author: Optional[str] = None
    language: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    summary: Optional[str] = None
    
    # Structure info
    page_count: Optional[int] = None
    section_count: Optional[int] = None
    code_block_count: Optional[int] = None
    table_count: Optional[int] = None
    
    # Links and references
    links: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    
    # Quality metrics
    ocr_confidence: Optional[float] = None
    extraction_quality: Optional[str] = None  # 'high', 'medium', 'low'
    
    # Chunking info (for large documents)
    is_chunked: bool = False
    total_chunks: int = 1
    chunk_index: int = 0
    
    # Custom metadata from specific extractors
    custom: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "source_file": self.source_file,
            "source_mime_type": self.source_mime_type,
            "file_size_bytes": self.file_size_bytes,
            "extracted_at": self.extracted_at.isoformat(),
            "extractor": {
                "name": self.extractor.name,
                "version": self.extractor.version,
                "config": self.extractor.config
            },
            "extraction_duration_ms": self.extraction_duration_ms,
            "title": self.title,
            "author": self.author,
            "language": self.language,
            "keywords": self.keywords,
            "summary": self.summary,
            "page_count": self.page_count,
            "section_count": self.section_count,
            "code_block_count": self.code_block_count,
            "table_count": self.table_count,
            "links": self.links,
            "images": self.images,
            "ocr_confidence": self.ocr_confidence,
            "extraction_quality": self.extraction_quality,
            "is_chunked": self.is_chunked,
            "total_chunks": self.total_chunks,
            "chunk_index": self.chunk_index,
            "custom": self.custom
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentMetadata":
        """Create from dictionary (JSON deserialization)."""
        extractor_data = data.get("extractor", {})
        extractor = ExtractorInfo(
            name=extractor_data.get("name", "unknown"),
            version=extractor_data.get("version", "1.0"),
            config=extractor_data.get("config", {})
        )
        
        return cls(
            source_file=data["source_file"],
            source_mime_type=data["source_mime_type"],
            file_size_bytes=data["file_size_bytes"],
            extracted_at=datetime.fromisoformat(data["extracted_at"]),
            extractor=extractor,
            extraction_duration_ms=data.get("extraction_duration_ms"),
            title=data.get("title"),
            author=data.get("author"),
            language=data.get("language"),
            keywords=data.get("keywords", []),
            summary=data.get("summary"),
            page_count=data.get("page_count"),
            section_count=data.get("section_count"),
            code_block_count=data.get("code_block_count"),
            table_count=data.get("table_count"),
            links=data.get("links", []),
            images=data.get("images", []),
            ocr_confidence=data.get("ocr_confidence"),
            extraction_quality=data.get("extraction_quality"),
            is_chunked=data.get("is_chunked", False),
            total_chunks=data.get("total_chunks", 1),
            chunk_index=data.get("chunk_index", 0),
            custom=data.get("custom", {})
        )
