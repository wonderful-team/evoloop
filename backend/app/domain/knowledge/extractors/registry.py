"""
Extractor registry for managing and routing to extractors.
"""

import logging
from typing import Optional

from app.domain.knowledge.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class ExtractorRegistry:
    """
    Central registry for document extractors.
    
    This registry manages all available extractors and routes files to the
    appropriate extractor based on MIME type and filename.
    
    Usage:
        # Register extractors
        ExtractorRegistry.register(PDFExtractor())
        ExtractorRegistry.register(HTMLExtractor())
        
        # Get extractor for a file
        extractor = await ExtractorRegistry.get_extractor("application/pdf", "doc.pdf")
        if extractor:
            doc = await extractor.extract(file, "doc.pdf")
    """
    
    _extractors: list[BaseExtractor] = []
    _initialized: bool = False
    
    @classmethod
    def register(cls, extractor: BaseExtractor) -> None:
        """
        Register an extractor.
        
        Args:
            extractor: The extractor instance to register
        
        Example:
            ExtractorRegistry.register(PDFExtractor())
        """
        cls._extractors.append(extractor)
        # Sort by priority (lower = higher priority)
        cls._extractors.sort(key=lambda e: e.priority())
        logger.info(f"Registered extractor: {extractor.name} (priority: {extractor.priority()})")
    
    @classmethod
    def unregister(cls, name: str) -> bool:
        """
        Unregister an extractor by name.
        
        Args:
            name: The name of the extractor to unregister
        
        Returns:
            True if an extractor was removed
        """
        initial_count = len(cls._extractors)
        cls._extractors = [e for e in cls._extractors if e.name != name]
        removed = len(cls._extractors) < initial_count
        if removed:
            logger.info(f"Unregistered extractor: {name}")
        return removed
    
    @classmethod
    async def get_extractor(
        cls, 
        mime_type: str, 
        filename: str
    ) -> Optional[BaseExtractor]:
        """
        Get the best extractor for a file.
        
        Args:
            mime_type: The MIME type of the file
            filename: The original filename
        
        Returns:
            The best matching extractor, or None if no extractor supports the file
        
        The selection process:
        1. Find all extractors that support the file
        2. Filter to only available ones (dependencies installed)
        3. Return the one with lowest priority value
        """
        candidates = []
        
        for extractor in cls._extractors:
            try:
                if extractor.supports(mime_type, filename):
                    candidates.append(extractor)
            except Exception as e:
                logger.warning(f"Extractor {extractor.name} failed supports check: {e}")
        
        if not candidates:
            return None
        
        # Filter to available extractors and sort by priority
        available = []
        for extractor in candidates:
            try:
                if await extractor.is_available():
                    available.append(extractor)
            except Exception:
                # If is_available() fails, assume not available
                pass
        
        if not available:
            logger.warning(f"No available extractor for {filename} ({mime_type})")
            return None
        
        # Return highest priority (lowest number)
        best = min(available, key=lambda e: e.priority())
        logger.debug(f"Selected extractor {best.name} for {filename}")
        return best
    
    @classmethod
    def get_extractor_by_name(cls, name: str) -> Optional[BaseExtractor]:
        """
        Get an extractor by its name.
        
        Args:
            name: The extractor name
        
        Returns:
            The extractor, or None if not found
        """
        for extractor in cls._extractors:
            if extractor.name == name:
                return extractor
        return None
    
    @classmethod
    async def list_extractors(cls) -> list[dict]:
        """
        List all registered extractors with their capabilities.
        
        Returns:
            List of extractor info dictionaries
        """
        result = []
        for e in cls._extractors:
            try:
                available = await e.is_available()
            except Exception:
                available = False
            result.append({
                "name": e.name,
                "version": e.version,
                "priority": e.priority(),
                "available": available
            })
        return result
    
    @classmethod
    def list_supported_types(cls) -> list[str]:
        """
        Get a list of all supported MIME types.
        
        Returns:
            List of MIME type strings
        """
        types = set()
        # This is heuristic - extractors should ideally declare their types
        for extractor in cls._extractors:
            # Try to infer from extractor name or docstring
            name_lower = extractor.name.lower()
            if "pdf" in name_lower:
                types.add("application/pdf")
            elif "html" in name_lower:
                types.add("text/html")
            elif "image" in name_lower or "ocr" in name_lower:
                types.add("image/*")
            elif "word" in name_lower:
                types.add("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            elif "excel" in name_lower:
                types.add("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            elif "powerpoint" in name_lower:
                types.add("application/vnd.openxmlformats-officedocument.presentationml.presentation")
        return sorted(types)
    
    @classmethod
    def clear(cls) -> None:
        """Clear all registered extractors (mainly for testing)."""
        cls._extractors.clear()
        logger.info("Cleared all extractors")
    
    @classmethod
    def initialize_defaults(cls) -> None:
        """
        Initialize with default extractors.
        
        This should be called at application startup.
        """
        if cls._initialized:
            return
        
        logger.info("Initializing default extractors...")
        
        # Import and register built-in extractors
        try:
            from .text import PlainTextExtractor, MarkdownExtractor, CodeDocExtractor
            cls.register(PlainTextExtractor())
            cls.register(MarkdownExtractor())
            cls.register(CodeDocExtractor())
            logger.info("Registered text extractors")
        except Exception as e:
            logger.warning(f"Failed to register text extractors: {e}")
        
        # HTML Extractor
        try:
            from .html import HTMLExtractor
            cls.register(HTMLExtractor())
            logger.info("Registered HTML extractor")
        except Exception as e:
            logger.warning(f"Failed to register HTML extractor: {e}")
        
        # PDF Extractors
        try:
            from .pdf import PDFExtractor, PyPDF2Extractor
            cls.register(PDFExtractor())
            cls.register(PyPDF2Extractor())
            logger.info("Registered PDF extractors")
        except Exception as e:
            logger.warning(f"Failed to register PDF extractors: {e}")
        
        # Office Extractors
        try:
            from .office import WordExtractor, ExcelExtractor, PowerPointExtractor
            cls.register(WordExtractor())
            cls.register(ExcelExtractor())
            cls.register(PowerPointExtractor())
            logger.info("Registered Office extractors")
        except Exception as e:
            logger.warning(f"Failed to register Office extractors: {e}")
        
        # Image OCR Extractors
        try:
            from .image import ImageOCRExtractor, ScreenshotExtractor
            cls.register(ImageOCRExtractor())
            cls.register(ScreenshotExtractor())
            logger.info("Registered image OCR extractors")
        except Exception as e:
            logger.warning(f"Failed to register image OCR extractors: {e}")
        
        cls._initialized = True
        logger.info(f"Extractor registry initialized with {len(cls._extractors)} extractors")


# Convenience function for routing
async def get_extractor_for_file(mime_type: str, filename: str) -> Optional[BaseExtractor]:
    """
    Convenience function to get extractor without importing the class.
    
    Example:
        extractor = await get_extractor_for_file("application/pdf", "doc.pdf")
        if extractor:
            doc = await extractor.extract(file, "doc.pdf")
    """
    return await ExtractorRegistry.get_extractor(mime_type, filename)
