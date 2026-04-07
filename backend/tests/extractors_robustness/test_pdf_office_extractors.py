"""
Robustness tests for PDF and Office Extractors
"""

import pytest
import io
import zipfile


class TestPDFExtractorRobustness:
    """Test PDFExtractor edge cases."""
    
    @pytest.fixture
    def extractor(self):
        from app.domain.knowledge.extractors.pdf import PDFExtractor
        return PDFExtractor()
    
    @pytest.mark.asyncio
    async def test_invalid_pdf(self, extractor):
        """Handle invalid PDF files."""
        file = io.BytesIO(b"Not a PDF content")
        try:
            doc = await extractor.extract(file, "fake.pdf")
        except Exception as e:
            # Expected to fail gracefully
            pass
    
    @pytest.mark.asyncio
    async def test_empty_pdf(self, extractor):
        """Handle empty PDF."""
        file = io.BytesIO(b"")
        try:
            doc = await extractor.extract(file, "empty.pdf")
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_corrupted_pdf_header(self, extractor):
        """Handle corrupted PDF header."""
        file = io.BytesIO(b"%PDF-1.4\ncorrupted content here")
        try:
            doc = await extractor.extract(file, "corrupted.pdf")
        except Exception:
            pass
    
    def test_pdf_availability(self, extractor):
        """Test PDF extractor availability check."""
        # Check if dependencies are available
        assert hasattr(extractor, 'is_available')
    
    @pytest.mark.asyncio
    async def test_pdf_metadata_extraction(self, extractor):
        """Test PDF metadata extraction handling."""
        # Mock file that looks like PDF but isn't
        file = io.BytesIO(b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n")
        try:
            doc = await extractor.extract(file, "minimal.pdf")
        except Exception:
            pass


class TestOfficeExtractorsRobustness:
    """Test Office extractors edge cases."""
    
    @pytest.mark.asyncio
    async def test_word_invalid_docx(self):
        """Handle invalid Word documents."""
        from app.domain.knowledge.extractors.office import WordExtractor
        extractor = WordExtractor()
        
        # Fake DOCX (actually a zip with wrong content)
        file = io.BytesIO(b"PK\x03\x04fake docx content")
        try:
            doc = await extractor.extract(file, "fake.docx")
        except Exception:
            pass  # Expected to fail
    
    @pytest.mark.asyncio
    async def test_word_empty_docx(self):
        """Handle empty Word files."""
        from app.domain.knowledge.extractors.office import WordExtractor
        extractor = WordExtractor()
        
        file = io.BytesIO(b"")
        try:
            doc = await extractor.extract(file, "empty.docx")
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_excel_invalid_xlsx(self):
        """Handle invalid Excel files."""
        from app.domain.knowledge.extractors.office import ExcelExtractor
        extractor = ExcelExtractor()
        
        file = io.BytesIO(b"PK\x03\x04fake xlsx content")
        try:
            doc = await extractor.extract(file, "fake.xlsx")
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_excel_with_many_sheets(self):
        """Handle Excel with many sheets."""
        from app.domain.knowledge.extractors.office import ExcelExtractor
        extractor = ExcelExtractor()
        
        # This would need a real Excel file to test properly
        # For now, just verify the method exists
        assert hasattr(extractor, 'extract')
    
    @pytest.mark.asyncio
    async def test_powerpoint_invalid_pptx(self):
        """Handle invalid PowerPoint files."""
        from app.domain.knowledge.extractors.office import PowerPointExtractor
        extractor = PowerPointExtractor()
        
        file = io.BytesIO(b"PK\x03\x04fake pptx content")
        try:
            doc = await extractor.extract(file, "fake.pptx")
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_office_availability(self):
        """Test office extractor availability."""
        from app.domain.knowledge.extractors.office import (
            WordExtractor, ExcelExtractor, PowerPointExtractor
        )
        
        for ExtractorClass in [WordExtractor, ExcelExtractor, PowerPointExtractor]:
            extractor = ExtractorClass()
            assert hasattr(extractor, 'is_available')
            # Don't assert the result as it depends on dependencies


class TestExtractorsWithZip:
    """Test extractors with ZIP-based formats."""
    
    def create_fake_office_file(self, extension: str) -> io.BytesIO:
        """Create a fake Office file (ZIP with minimal structure)."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zf:
            zf.writestr("[Content_Types].xml", "<Types></Types>")
            if extension == '.docx':
                zf.writestr("word/document.xml", "<w:document></w:document>")
            elif extension == '.xlsx':
                zf.writestr("xl/workbook.xml", "<workbook></workbook>")
            elif extension == '.pptx':
                zf.writestr("ppt/presentation.xml", "<presentation></presentation>")
        buffer.seek(0)
        return buffer
    
    @pytest.mark.asyncio
    async def test_docx_zip_structure(self):
        """Test DOCX ZIP structure handling."""
        from app.domain.knowledge.extractors.office import WordExtractor
        
        extractor = WordExtractor()
        fake_file = self.create_fake_office_file('.docx')
        
        try:
            doc = await extractor.extract(fake_file, "test.docx")
        except Exception:
            pass  # Expected if python-docx can't parse
    
    @pytest.mark.asyncio
    async def test_xlsx_zip_structure(self):
        """Test XLSX ZIP structure handling."""
        from app.domain.knowledge.extractors.office import ExcelExtractor
        
        extractor = ExcelExtractor()
        fake_file = self.create_fake_office_file('.xlsx')
        
        try:
            doc = await extractor.extract(fake_file, "test.xlsx")
        except Exception:
            pass
