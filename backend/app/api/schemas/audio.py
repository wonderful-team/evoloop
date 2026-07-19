"""API schemas for audio routes (STT only)."""

from typing import Any

from app.api.schemas.responses import BaseAPIResponse


class TranscriptionResponse(BaseAPIResponse):
    text: str
    duration: float
    language: str
    confidence: float | None = None


class STTProvidersResponse(BaseAPIResponse):
    providers: list[dict[str, Any]]
