"""
Core document models for knowledge extraction.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, BinaryIO, Optional


@dataclass
class MarkdownDocument:
    """
    Represents a document extracted to Markdown format.
    
    This is the universal format for all extracted content in the knowledge base.
    """
    content: str
    source: str                    # Original filename/path
    mime_type: str                 # Original MIME type
    metadata: dict[str, Any] = field(default_factory=dict)
    extracted_at: datetime = field(default_factory=datetime.utcnow)
    
    # Optional chunking for large documents
    chunks: Optional[list[str]] = None
    
    def __post_init__(self):
        """Validate document content."""
        if not self.content:
            self.content = ""
        
        # Ensure metadata has required fields
        if "source" not in self.metadata:
            self.metadata["source"] = self.source
        if "extracted_at" not in self.metadata:
            self.metadata["extracted_at"] = self.extracted_at.isoformat()
    
    @property
    def size(self) -> int:
        """Get content size in bytes."""
        return len(self.content.encode('utf-8'))
    
    @property
    def line_count(self) -> int:
        """Get number of lines in content."""
        return len(self.content.split('\n'))
    
    def get_chunk(self, index: int) -> Optional[str]:
        """Get specific chunk if document was chunked."""
        if self.chunks and 0 <= index < len(self.chunks):
            return self.chunks[index]
        return None
    
    def to_frontmatter(self) -> str:
        """
        Convert to Markdown with YAML frontmatter.
        This is the storage format for the knowledge base.
        """
        import yaml
        
        # Build frontmatter
        frontmatter = {
            "source": self.source,
            "mime_type": self.mime_type,
            "extracted_at": self.extracted_at.isoformat(),
            **self.metadata
        }
        
        # Convert to YAML
        yaml_content = yaml.safe_dump(
            frontmatter, 
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False
        )
        
        return f"---\n{yaml_content}---\n\n{self.content}"
    
    @classmethod
    def from_frontmatter(cls, text: str) -> "MarkdownDocument":
        """Parse a Markdown document with YAML frontmatter."""
        import yaml
        
        if not text.startswith('---'):
            # No frontmatter, treat as plain content
            return cls(
                content=text,
                source="unknown",
                mime_type="text/plain",
                metadata={}
            )
        
        # Split frontmatter and content
        parts = text.split('---', 2)
        if len(parts) < 3:
            return cls(
                content=text,
                source="unknown",
                mime_type="text/plain",
                metadata={}
            )
        
        try:
            metadata = yaml.safe_load(parts[1]) or {}
        except Exception:
            metadata = {}
        
        content = parts[2].strip()
        
        return cls(
            content=content,
            source=metadata.get("source", "unknown"),
            mime_type=metadata.get("mime_type", "text/plain"),
            metadata={k: v for k, v in metadata.items() 
                     if k not in ("source", "mime_type", "extracted_at")},
            extracted_at=datetime.fromisoformat(metadata.get("extracted_at", datetime.utcnow().isoformat()))
        )


class ExtractionError(Exception):
    """Raised when document extraction fails."""
    
    def __init__(self, message: str, source: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(message)
        self.source = source
        self.details = details or {}
