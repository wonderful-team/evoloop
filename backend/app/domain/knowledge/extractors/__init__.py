"""
Document extractors for converting various file formats to Markdown.

This module provides extractors for:
- Text files (plain text, markdown, code)
- Web content (HTML)
- Documents (PDF, Word, Excel, PowerPoint)
- Images (OCR for text extraction)
"""

from app.domain.knowledge.extractors.base import BaseExtractor, ExtractionError
from app.domain.knowledge.extractors.registry import (
    ExtractorRegistry,
    get_extractor_for_file
)

# Text extractors
from app.domain.knowledge.extractors.text import (
    PlainTextExtractor,
    MarkdownExtractor,
    CodeDocExtractor
)

# HTML extractor
from app.domain.knowledge.extractors.html import HTMLExtractor

# PDF extractors
from app.domain.knowledge.extractors.pdf import PDFExtractor, PyPDF2Extractor

# Office extractors
from app.domain.knowledge.extractors.office import (
    WordExtractor,
    ExcelExtractor,
    PowerPointExtractor
)

# Image OCR extractors
from app.domain.knowledge.extractors.image import (
    ImageOCRExtractor,
    ScreenshotExtractor
)

__all__ = [
    # Base classes
    "BaseExtractor",
    "ExtractionError",
    
    # Registry
    "ExtractorRegistry",
    "get_extractor_for_file",
    
    # Text
    "PlainTextExtractor",
    "MarkdownExtractor",
    "CodeDocExtractor",
    
    # Web
    "HTMLExtractor",
    
    # PDF
    "PDFExtractor",
    "PyPDF2Extractor",
    
    # Office
    "WordExtractor",
    "ExcelExtractor",
    "PowerPointExtractor",
    
    # Images
    "ImageOCRExtractor",
    "ScreenshotExtractor",
]
