"""
Image OCR extractor using Vision framework or pytesseract.
"""

import logging
import tempfile
from typing import BinaryIO

from app.domain.knowledge.extractors.base import BaseExtractor
from app.domain.knowledge.models import MarkdownDocument

logger = logging.getLogger(__name__)


class ImageOCRExtractor(BaseExtractor):
    """
    Extractor for images using OCR.
    
    Extracts text content from images (PNG, JPG, etc.) using:
    1. MacOS Vision framework (preferred on Mac)
    2. pytesseract (fallback, requires Tesseract)
    3. EasyOCR (alternative, no Tesseract needed)
    
    Images without text are described using a vision model.
    """
    
    SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', '.webp'}
    SUPPORTED_MIME_TYPES = {
        'image/png', 'image/jpeg', 'image/gif', 'image/bmp',
        'image/tiff', 'image/webp'
    }
    
    @property
    def name(self) -> str:
        return "image_ocr"
    
    def priority(self) -> int:
        return 10
    
    def supports(self, mime_type: str, filename: str) -> bool:
        """Check if file is an image."""
        ext = self._get_file_extension(filename)
        if ext in self.SUPPORTED_EXTENSIONS:
            return True
        if mime_type.startswith('image/'):
            return True
        return False
    
    async def extract(self, file: BinaryIO, filename: str) -> MarkdownDocument:
        """Extract text from image using OCR."""
        content = self._read_all(file)
        
        # Save to temp file
        ext = self._get_file_extension(filename)
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            temp_path = tmp.name
        
        try:
            # Try MacOS Vision first (best quality on Mac)
            text = await self._try_macos_vision(temp_path)
            ocr_engine = "macos_vision"
            
            if text is None:
                # Fallback to pytesseract
                text = await self._try_pytesseract(temp_path)
                ocr_engine = "pytesseract"
            
            if text is None:
                # Fallback to EasyOCR
                text = await self._try_easyocr(temp_path)
                ocr_engine = "easyocr"
            
            if text is None:
                # No OCR available - describe the image
                text = await self._describe_image(temp_path)
                ocr_engine = "vision_description"
            
            # Build document
            header = f"# Image: {filename}\n\n"
            
            if ocr_engine == "vision_description":
                header += "## Image Description\n\n"
            else:
                header += f"## Extracted Text (via {ocr_engine})\n\n"
            
            return MarkdownDocument(
                content=f"{header}{text}",
                source=filename,
                mime_type=f"image/{ext.lstrip('.')}",
                metadata={
                    "ocr_engine": ocr_engine,
                    "original_size": len(content),
                    "extracted_length": len(text),
                }
            )
        
        finally:
            import os
            os.unlink(temp_path)
    
    async def _try_macos_vision(self, image_path: str) -> str | None:
        """Try MacOS Vision OCR."""
        try:
            from app.core.vision.providers.ocr.macos_vision import MacOSVisionOCRProvider
            from app.core.vision.types import VisionTask
            
            provider = MacOSVisionOCRProvider()
            
            if not await provider.is_available():
                return None
            
            result = await provider.process(
                task=VisionTask.OCR,
                image_source=image_path
            )
            
            if result.success and result.elements:
                # Concatenate all text elements
                texts = [e.text for e in result.elements if e.text]
                return '\n'.join(texts)
            
            return None
        
        except Exception as e:
            logger.debug(f"MacOS Vision OCR failed: {e}")
            return None
    
    async def _try_pytesseract(self, image_path: str) -> str | None:
        """Try pytesseract OCR."""
        try:
            import pytesseract
            from PIL import Image
            
            image = Image.open(image_path)
            text = pytesseract.image_to_string(image, lang='chi_sim+eng')
            return text.strip() if text.strip() else None
        
        except Exception as e:
            logger.debug(f"pytesseract OCR failed: {e}")
            return None
    
    async def _try_easyocr(self, image_path: str) -> str | None:
        """Try EasyOCR."""
        try:
            import easyocr
            
            reader = easyocr.Reader(['ch_sim', 'en'])
            results = reader.readtext(image_path)
            
            texts = [r[1] for r in results]
            return '\n'.join(texts) if texts else None
        
        except Exception as e:
            logger.debug(f"EasyOCR failed: {e}")
            return None
    
    async def _describe_image(self, image_path: str) -> str:
        """Describe image using vision model when OCR is not available."""
        # Placeholder - future implementation would use vision model
        return "[Image content - no text extracted]"


class ScreenshotExtractor(ImageOCRExtractor):
    """
    Specialized extractor for screenshots.
    
    Same as ImageOCRExtractor but with higher confidence that
    text is present and should be extracted.
    """
    
    @property
    def name(self) -> str:
        return "screenshot_ocr"
    
    def priority(self) -> int:
        """Higher priority for screenshots."""
        return 5
    
    def supports(self, mime_type: str, filename: str) -> bool:
        """Check if file looks like a screenshot."""
        ext = self._get_file_extension(filename)
        name_lower = filename.lower()
        
        # Check for screenshot naming patterns
        screenshot_patterns = ['screenshot', 'screen', 'screencapture', '截屏', '屏幕']
        is_screenshot = any(p in name_lower for p in screenshot_patterns)
        
        # PNG files are often screenshots on Mac
        is_png_screenshot = ext == '.png' and ('png' in name_lower or 'image' in name_lower)
        
        return is_screenshot or is_png_screenshot or super().supports(mime_type, filename)
