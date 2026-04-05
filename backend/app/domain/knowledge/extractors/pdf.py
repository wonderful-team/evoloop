"""
PDF extractor using PyPDF2 or pdfplumber.
"""

import logging
from typing import BinaryIO

from app.domain.knowledge.extractors.base import BaseExtractor
from app.domain.knowledge.models import MarkdownDocument, ExtractionError

logger = logging.getLogger(__name__)


class PDFExtractor(BaseExtractor):
    """
    Extractor for PDF files.
    
    Extracts text content from PDF documents, preserving page structure.
    Falls back to OCR if the PDF contains scanned images.
    
    Requires: pip install pdfplumber pillow
    """
    
    @property
    def name(self) -> str:
        return "pdf"
    
    def priority(self) -> int:
        """High priority for PDFs."""
        return 10
    
    def supports(self, mime_type: str, filename: str) -> bool:
        """Check if file is PDF."""
        ext = self._get_file_extension(filename)
        if ext == '.pdf':
            return True
        if mime_type == 'application/pdf':
            return True
        return False
    
    async def is_available(self) -> bool:
        """Check if pdfplumber is installed."""
        try:
            import pdfplumber
            return True
        except ImportError:
            return False
    
    async def extract(self, file: BinaryIO, filename: str) -> MarkdownDocument:
        """Extract text from PDF."""
        try:
            import pdfplumber
        except ImportError:
            raise ExtractionError(
                "pdfplumber not installed. Run: pip install pdfplumber",
                source=filename
            )
        
        content = self._read_all(file)
        
        # Save to temp file (pdfplumber needs file path)
        temp_path = self._save_temp(file, suffix='.pdf')
        
        try:
            text_content = []
            metadata = {}
            has_text = False
            
            with pdfplumber.open(temp_path) as pdf:
                # Extract metadata
                if pdf.metadata:
                    metadata = {
                        "title": pdf.metadata.get('Title', ''),
                        "author": pdf.metadata.get('Author', ''),
                        "creator": pdf.metadata.get('Creator', ''),
                        "producer": pdf.metadata.get('Producer', ''),
                        "creation_date": pdf.metadata.get('CreationDate', ''),
                        "modification_date": pdf.metadata.get('ModDate', ''),
                        "page_count": len(pdf.pages),
                    }
                
                # Extract text from each page
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        has_text = True
                        text_content.append(f"## Page {i + 1}\n\n{page_text}")
            
            # If no text found, it might be a scanned PDF - needs OCR
            if not has_text:
                logger.info(f"PDF appears to be scanned, needs OCR: {filename}")
                metadata["needs_ocr"] = True
                metadata["is_scanned"] = True
                
                # Try OCR if available
                ocr_result = await self._try_ocr(temp_path)
                if ocr_result:
                    text_content = ocr_result
                    metadata["ocr_extracted"] = True
            
            # Build final content
            title = metadata.get('title', filename)
            header = f"# {title}\n\n" if title != filename else ""
            
            final_content = f"{header}Source: {filename}\n\n"
            final_content += "\n\n---\n\n".join(text_content)
            
            return MarkdownDocument(
                content=final_content,
                source=filename,
                mime_type="application/pdf",
                metadata=metadata
            )
        
        finally:
            import os
            os.unlink(temp_path)
    
    async def _try_ocr(self, pdf_path: str) -> list[str]:
        """
        Try to OCR a scanned PDF.
        
        This requires additional dependencies: pdf2image, pytesseract
        """
        try:
            from pdf2image import convert_from_path
            import pytesseract
            
            pages = convert_from_path(pdf_path)
            text_content = []
            
            for i, page in enumerate(pages):
                text = pytesseract.image_to_string(page)
                text_content.append(f"## Page {i + 1}\n\n{text}")
            
            return text_content
        
        except Exception as e:
            logger.warning(f"OCR failed: {e}")
            return ["## OCR Required\n\nThis PDF appears to be scanned and contains no extractable text. OCR is required to extract content."]
    
    def get_metadata(self, file: BinaryIO, filename: str) -> dict:
        """Extract PDF metadata without full text extraction."""
        try:
            import pdfplumber
        except ImportError:
            return {}
        
        temp_path = self._save_temp(file, suffix='.pdf')
        try:
            with pdfplumber.open(temp_path) as pdf:
                return {
                    "page_count": len(pdf.pages),
                    **{k.lower(): v for k, v in (pdf.metadata or {}).items()}
                }
        except Exception:
            return {}
        finally:
            import os
            os.unlink(temp_path)


class PyPDF2Extractor(BaseExtractor):
    """
    Fallback PDF extractor using PyPDF2 (lighter dependency).
    
    Use this if pdfplumber is not available.
    """
    
    @property
    def name(self) -> str:
        return "pdf_pypdf2"
    
    def priority(self) -> int:
        """Lower priority than pdfplumber."""
        return 50
    
    def supports(self, mime_type: str, filename: str) -> bool:
        """Check if file is PDF."""
        ext = self._get_file_extension(filename)
        return ext == '.pdf' or mime_type == 'application/pdf'
    
    async def is_available(self) -> bool:
        """Check if PyPDF2 is installed and working."""
        try:
            import PyPDF2
            # Try to actually use it to catch architecture issues
            from PyPDF2 import PdfReader
            return True
        except Exception:
            return False
    
    async def extract(self, file: BinaryIO, filename: str) -> MarkdownDocument:
        """Extract text using PyPDF2."""
        try:
            import PyPDF2
        except ImportError:
            raise ExtractionError(
                "PyPDF2 not installed. Run: pip install PyPDF2",
                source=filename
            )
        
        content = self._read_all(file)
        
        try:
            reader = PyPDF2.PdfReader(file)
            
            text_content = []
            metadata = {}
            
            # Extract metadata
            if reader.metadata:
                meta = reader.metadata
                metadata = {
                    "title": meta.get('/Title', ''),
                    "author": meta.get('/Author', ''),
                    "creator": meta.get('/Creator', ''),
                    "page_count": len(reader.pages),
                }
            
            # Extract text from each page
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text_content.append(f"## Page {i + 1}\n\n{page_text}")
            
            # Build final content
            title = metadata.get('title', filename)
            header = f"# {title}\n\n" if title != filename else ""
            
            final_content = f"{header}Source: {filename}\n\n"
            final_content += "\n\n---\n\n".join(text_content)
            
            return MarkdownDocument(
                content=final_content,
                source=filename,
                mime_type="application/pdf",
                metadata=metadata
            )
        
        except Exception as e:
            raise ExtractionError(
                f"Failed to extract PDF: {str(e)}",
                source=filename,
                details={"error_type": type(e).__name__}
            )
