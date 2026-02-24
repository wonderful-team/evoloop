import logging
import os

import mammoth
import pandas as pd
from markdownify import markdownify as md
from pypdf import PdfReader

from app.core.vision import VisionTask, vision_engine
from app.utils.file import read_file_content

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
                return self._read_html(file_path)
            elif ext in [".png", ".jpg", ".jpeg", ".bmp", ".webp"]:
                return await self._read_image(file_path)
            elif ext in [".mp3", ".wav", ".mp4", ".mov", ".avi"]:
                return await self._read_media(file_path)
            else:
                # Text/Code fallback with paging support
                content, _ = read_file_content(file_path, start_page, end_page)
                return content
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
        # We omit the metadata and headers from core reader to stay clean for indexing
        # but could add them if needed.
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
            # OPTIMIZATION: Use the already opened 'xl' object instead of re-reading file Path
            df = pd.read_excel(xl, sheet_name=sheet_name)
            if not df.empty:
                text.append(f"### Sheet: {sheet_name}\n")
                try:
                    text.append(df.to_markdown(index=False))
                except ImportError:
                    # Fallback if tabulate is not installed
                    text.append(df.to_csv(index=False))
                text.append("\n")
        return "\n".join(text)

    def _read_html(self, path: str) -> str:
        with open(path, encoding="utf-8") as f:
            html_content = f.read()
        return md(html_content)

    async def _read_image(self, path: str) -> str:
        """Extract text from image using OCR."""
        try:
            result = await vision_engine.process(
                task=VisionTask.OCR,
                image_source=path
            )
            if not result.success:
                return f"[OCR Error: {result.metadata.get('error')}]"

            texts = [el.text for el in result.elements if el.text]
            return "\n".join(texts)
        except Exception as e:
            logger.error(f"OCR failed for {path}: {e}")
            return f"[OCR Error: {str(e)}]"

    async def _read_media(self, path: str) -> str:
        """Transcribe audio/video to text."""
        # TODO: Integrate with Whisper / OpenAI Speech-to-Text
        # For now, return a placeholder as a signal.
        return f"[Multimedia Asset: Transcription for {os.path.basename(path)} is pending integration]"


document_reader_service = DocumentReaderService()
