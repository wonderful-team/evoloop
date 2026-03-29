"""TTS Provider Base - Re-export from base module"""
from app.core.voice.base import BaseTTSProvider, TTSOptions, TTSSResult, Voice, VoiceGender, VoiceLocale

__all__ = ["BaseTTSProvider", "TTSOptions", "TTSSResult", "Voice", "VoiceGender", "VoiceLocale"]
