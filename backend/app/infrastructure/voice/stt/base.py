"""STT Provider Base - Re-export from base module"""

from app.infrastructure.voice.base import (
    BaseSTTProvider,
    STTOptions,
    STTResult,
    VoiceGender,
    VoiceLocale,
)

__all__ = ["BaseSTTProvider", "STTOptions", "STTResult", "VoiceGender", "VoiceLocale"]
