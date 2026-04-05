"""
Abstract base class for all document extractors.
"""

from abc import ABC, abstractmethod
from typing import BinaryIO, Optional

from app.domain.knowledge.models import MarkdownDocument, ExtractionError


class BaseExtractor(ABC):
    """
    Abstract base class for all document extractors.
    
    An extractor's responsibility is to convert a file from its native format
    into Markdown, which is the universal format for the knowledge base.
    
    Implementations should:
    1. Handle specific file formats (PDF, Word, HTML, etc.)
    2. Preserve document structure (headings, lists, tables)
    3. Extract metadata (title, author, pages, etc.)
    4. Handle errors gracefully with meaningful messages
    
    Example:
        class PDFExtractor(BaseExtractor):
            @property
            def name(self) -> str:
                return "pdf"
            
            def supports(self, mime_type: str, filename: str) -> bool:
                return mime_type == "application/pdf" or filename.endswith(".pdf")
            
            async def extract(self, file: BinaryIO, filename: str) -> MarkdownDocument:
                # Implementation here
                pass
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the unique name of this extractor.
        
        This is used for logging and metadata purposes.
        """
        pass
    
    @property
    def version(self) -> str:
        """
        Return the version of this extractor.
        
        Default is "1.0". Override if you need version tracking.
        """
        return "1.0"
    
    @abstractmethod
    def supports(self, mime_type: str, filename: str) -> bool:
        """
        Check if this extractor supports the given file.
        
        Args:
            mime_type: The MIME type of the file (may be empty or generic)
            filename: The original filename (with extension)
        
        Returns:
            True if this extractor can handle the file
        
        Note:
            This method should be fast and not read the file content.
            It's used for routing to the correct extractor.
        """
        pass
    
    @abstractmethod
    async def extract(self, file: BinaryIO, filename: str) -> MarkdownDocument:
        """
        Extract the file content to Markdown.
        
        Args:
            file: Binary file-like object (already opened for reading)
            filename: Original filename (for extension checking and metadata)
        
        Returns:
            MarkdownDocument containing the extracted content and metadata
        
        Raises:
            ExtractionError: If extraction fails
        
        Note:
            - The file object may be at any position; implementations should
              seek to the beginning if needed
            - Implementations should handle large files efficiently
            - Errors should be raised as ExtractionError with context
        """
        pass
    
    def priority(self) -> int:
        """
        Return the priority of this extractor (lower = higher priority).
        
        When multiple extractors support the same file type, the one with
        the lowest priority value is chosen.
        
        Default is 100. Specialized extractors should use lower values.
        """
        return 100
    
    async def is_available(self) -> bool:
        """
        Check if this extractor is available (dependencies installed, etc.).
        
        Returns:
            True if the extractor can be used
        
        Override this if your extractor has optional dependencies.
        """
        return True
    
    def get_metadata(self, file: BinaryIO, filename: str) -> dict:
        """
        Extract metadata without full content extraction.
        
        This is optional - for formats where metadata extraction is expensive,
        you can return an empty dict.
        
        Args:
            file: Binary file-like object
            filename: Original filename
        
        Returns:
            Dictionary of metadata (title, author, pages, etc.)
        """
        return {}
    
    def _get_file_extension(self, filename: str) -> str:
        """Helper to get lowercase file extension."""
        import os
        return os.path.splitext(filename)[1].lower()
    
    def _read_all(self, file: BinaryIO) -> bytes:
        """Helper to read all content from a binary file."""
        current_pos = file.tell()
        file.seek(0)
        content = file.read()
        file.seek(current_pos)
        return content
    
    def _save_temp(self, file: BinaryIO, suffix: str = "") -> str:
        """
        Helper to save binary content to a temporary file.
        
        Some libraries require file paths instead of file objects.
        Returns the path to the temporary file (caller must delete).
        """
        import tempfile
        import os
        
        fd, path = tempfile.mkstemp(suffix=suffix)
        try:
            os.close(fd)
            current_pos = file.tell()
            file.seek(0)
            with open(path, 'wb') as f:
                f.write(file.read())
            file.seek(current_pos)
            return path
        except Exception:
            os.unlink(path)
            raise
