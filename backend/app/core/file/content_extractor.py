import logging
import os

from .document_reader import document_reader_service
from .image_reader import image_reader_service
from .io import read_file
from .media_reader import media_reader_service

logger = logging.getLogger(__name__)


class FileContentExtractor:
    """
    Unified entry point for extracting text content from any file type.
    Routes to specialized services based on file extension.
    """

    async def extract(
        self,
        file_path: str,
        start_range: int | None = None,
        end_range: int | None = None,
    ) -> str:
        """
        Extract text from file. Automatically routes to Document, Image, Media
        or Plain Text readers.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()

        # 1. Documents (PDF, Docx, Excel, HTML)
        if ext in [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".html"]:
            return await document_reader_service.read_document(
                file_path=file_path,
                start_page=start_range,
                end_page=end_range
            )

        # 2. Images (OCR)
        if ext in [".png", ".jpg", ".jpeg", ".bmp", ".webp"]:
            return await image_reader_service.read(file_path)

        # 3. Multimedia (Transcription)
        if ext in [".mp3", ".wav", ".mp4", ".mov", ".avi"]:
            return await media_reader_service.read(file_path)

        # 4. Fallback: Plain Text / Code
        # We use the core io.read_file which supports pagination
        result = read_file(file_path, start_line=start_range, end_line=end_range)
        if not result.success:
            raise OSError(result.error_message or f"Failed to read text file: {file_path}")

        return result.content


content_extractor = FileContentExtractor()
