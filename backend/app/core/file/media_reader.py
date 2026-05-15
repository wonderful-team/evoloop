import logging
import os
from app.core.voice import transcribe_file, list_stt_providers

logger = logging.getLogger(__name__)

class MediaReaderService:
    """
    Specialized service for extracting text from multimedia files
    (Audio and Video) using speech-to-text providers.
    """

    async def read(self, path: str) -> str:
        """Transcribe audio/video to text."""
        try:
            # Check if any STT provider is available
            providers = list_stt_providers()
            if not any(p.get("available") for p in providers):
                return f"[Multimedia Asset: {os.path.basename(path)} - Transcription unavailable: No STT providers configured]"

            logger.info(f"Transcribing media file: {path}")
            result = await transcribe_file(path)
            
            if not result.text:
                return f"[Multimedia Asset: {os.path.basename(path)} - Transcription returned empty content]"
                
            return f"### Multimedia Transcription ({os.path.basename(path)})\n\n{result.text}"
            
        except Exception as e:
            logger.error(f"Media transcription failed for {path}: {e}")
            return f"[Multimedia Asset: {os.path.basename(path)} - Transcription Error: {str(e)}]"

media_reader_service = MediaReaderService()
