"""Audio processing API — STT endpoints removed.

Speech-to-Text is still available internally via
``app.infrastructure.voice.transcribe_file()`` for media file processing.
HTTP endpoints have been removed as the frontend uses Tauri native STT.
"""

from fastapi import APIRouter

router = APIRouter(tags=["audio"])
