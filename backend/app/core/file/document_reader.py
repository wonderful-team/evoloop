import logging
import os

import mammoth
import pandas as pd
from markdownify import markdownify as md
from pypdf import PdfReader

from app.core.vision import VisionTask, vision_engine
from .io import read_file

logger = logging.getLogger(__name__)


class DocumentReaderService:
    """
    Service to read and parse content from various document formats
    into Markdown for indexing and LLM consumption.
    """

    async def read_document(self, file_path: str, start_page: int | None = None, end_page: int | None = None) -> str:
        """Read various document formats and return Markdown string."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext in [".xlsx", ".xls"]:
                return self._read_excel(file_path)
            elif ext in [".docx", ".doc"]:
                return self._read_docx(file_path)
            elif ext == ".pdf":
                return self._read_pdf(file_path, start_page, end_page)
            elif ext == ".html":
                return await self._read_html(file_path)
            else:
                # Text/Code fallback handled by ContentExtractor normally, 
                # but kept here for backward compatibility or internal calls.
                result = read_file(file_path, start_line=start_page, end_line=end_page)
                if not result.success:
                    raise IOError(result.error_message or "Failed to read file")
                return result.content
        except Exception as e:
            logger.error(f"Failed to read document {file_path}: {e}")
            raise

    def _read_pdf(self, path: str, start: int | None, end: int | None) -> str:
        reader = PdfReader(path)
        total_pages = len(reader.pages)

        start_idx = (start - 1) if start else 0
        end_idx = end if end else total_pages
        start_idx = max(0, start_idx)
        end_idx = min(total_pages, end_idx)

        text = []
        for i in range(start_idx, end_idx):
            page_text = reader.pages[i].extract_text()
            text.append(page_text or "")

        return "\n\n".join(text)

    def _read_docx(self, path: str) -> str:
        with open(path, "rb") as docx_file:
            result = mammoth.convert_to_markdown(docx_file)
            return result.value

    def _read_excel(self, path: str) -> str:
        xl = pd.ExcelFile(path)
        text = []
        for sheet_name in xl.sheet_names:
            df = pd.read_excel(xl, sheet_name=sheet_name)
            if not df.empty:
                text.append(f"Sheet: {sheet_name}\n")
                try:
                    text.append(df.to_markdown(index=False))
                except ImportError:
                    text.append(df.to_csv(index=False))
                text.append("\n")
        return "\n".join(text)

    async def _read_html(self, file_path: str) -> str:
        result = read_file(file_path)
        if not result.success:
            return f"[Error reading HTML: {result.error_message}]"
        return md(result.content)


document_reader_service = DocumentReaderService()
