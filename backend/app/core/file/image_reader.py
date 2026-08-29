import logging
import os

from app.infrastructure.vision import VisionTask, vision_engine

logger = logging.getLogger(__name__)


class ImageReaderService:
    """
    Specialized service for extracting content from images
    using OCR or visual analysis.
    """

    async def read(self, path: str) -> str:
        """Extract text from image using OCR."""
        try:
            result = await vision_engine.process(task=VisionTask.OCR, image_source=path)
            if not result.success:
                return f"[OCR Error: {result.metadata.get('error')}]"

            texts = [el.text for el in result.elements if el.text]
            if not texts:
                return f"[Image Asset: {os.path.basename(path)} - No text found via OCR]"

            return f"### OCR Results ({os.path.basename(path)})\n\n" + "\n".join(texts)
        except Exception as e:
            logger.exception(f"OCR failed for {path}: {e}")
            return f"[OCR Error: {str(e)}]"


image_reader_service = ImageReaderService()
