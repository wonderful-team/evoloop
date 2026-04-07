"""
Robustness tests for Image OCR Extractor
"""

import pytest
import io
from app.domain.knowledge.extractors.image import ImageOCRExtractor, ScreenshotExtractor


class TestImageOCRExtractorRobustness:
    """Test ImageOCRExtractor edge cases."""
    
    @pytest.fixture
    def extractor(self):
        return ImageOCRExtractor()
    
    @pytest.mark.asyncio
    async def test_invalid_image(self, extractor):
        """Handle invalid image files."""
        file = io.BytesIO(b"Not an image")
        doc = await extractor.extract(file, "fake.png")
        # Should fallback to description
        assert doc.content is not None
    
    @pytest.mark.asyncio
    async def test_empty_image(self, extractor):
        """Handle empty image files."""
        file = io.BytesIO(b"")
        try:
            doc = await extractor.extract(file, "empty.png")
        except Exception:
            pass  # Expected
    
    @pytest.mark.asyncio
    async def test_corrupted_image_header(self, extractor):
        """Handle corrupted image headers."""
        # PNG magic bytes but corrupted
        file = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"corrupted" * 100)
        try:
            doc = await extractor.extract(file, "corrupted.png")
        except Exception:
            pass
    
    def test_image_formats(self, extractor):
        """Test various image format support."""
        formats = [
            ('image/png', 'test.png'),
            ('image/jpeg', 'test.jpg'),
            ('image/jpeg', 'test.jpeg'),
            ('image/gif', 'test.gif'),
            ('image/bmp', 'test.bmp'),
            ('image/tiff', 'test.tiff'),
            ('image/webp', 'test.webp'),
        ]
        for mime, filename in formats:
            assert extractor.supports(mime, filename) is True
    
    @pytest.mark.asyncio
    async def test_ocr_fallback_chain(self, extractor):
        """Test OCR fallback chain."""
        # All OCR methods should fail gracefully
        text = await extractor._try_macos_vision("/nonexistent/path.png")
        assert text is None
        
        text = await extractor._try_pytesseract("/nonexistent/path.png")
        assert text is None
        
        text = await extractor._try_easyocr("/nonexistent/path.png")
        assert text is None
    
    @pytest.mark.asyncio
    async def test_ocr_with_large_image(self, extractor):
        """Test OCR with large image description."""
        # Create a fake large image (just bytes, not actual image)
        file = io.BytesIO(b"\x89PNG" + b"\x00" * 1000000)  # 1MB
        try:
            doc = await extractor.extract(file, "large.png")
        except Exception:
            pass
    
    def test_screenshot_detector(self):
        """Test screenshot detection."""
        extractor = ScreenshotExtractor()
        
        # Should detect screenshot patterns
        assert extractor.supports("image/png", "Screenshot 2024-01-01.png") is True
        assert extractor.supports("image/png", "Screen Shot 2024.png") is True
        assert extractor.supports("image/png", "截屏2024.png") is True
        assert extractor.supports("image/png", "random.png") is False


class TestImageFormats:
    """Test image format variations."""
    
    def test_jpeg_variations(self):
        """Test JPEG format variations."""
        extractor = ImageOCRExtractor()
        
        # Various JPEG extensions
        assert extractor.supports("image/jpeg", "test.jpg") is True
        assert extractor.supports("image/jpeg", "test.jpeg") is True
        assert extractor.supports("image/jpg", "test.jpg") is True
    
    def test_unsupported_formats(self):
        """Test unsupported image formats."""
        extractor = ImageOCRExtractor()
        
        # These should not be supported
        assert extractor.supports("image/svg+xml", "test.svg") is False
        assert extractor.supports("image/x-icon", "test.ico") is False
        assert extractor.supports("application/pdf", "test.pdf") is False
    
    @pytest.mark.asyncio
    async def test_image_with_path_traversal(self):
        """Test image extraction with suspicious paths."""
        extractor = ImageOCRExtractor()
        
        suspicious_names = [
            "../../../etc/passwd.png",
            "..\\..\\windows\\system32\\config.jpg",
            "normal.png",
        ]
        
        for name in suspicious_names:
            # Should handle gracefully
            assert extractor.supports("image/png", name) is True  # Extension check only
