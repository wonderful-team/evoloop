"""STT Provider Base - Re-export from base module"""
from app.core.voice.base import (
    BaseSTTProvider,
    STTOptions,
    STTResult,
    Voice,
    VoiceGender,
    VoiceLocale,
)

__all__ = ["BaseSTTProvider", "STTOptions", "STTResult", "Voice", "VoiceGender", "VoiceLocale"]
