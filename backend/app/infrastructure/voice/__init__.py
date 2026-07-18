"""
EvoLoop Voice Module
语音模块 - 提供标准化的语音识别(STT)服务

TTS (Text-to-Speech) 已迁移到 Tauri 原生，不再由后端处理。
"""

from app.infrastructure.voice.base import (
    BaseSTTProvider,
    STTOptions,
    STTResult,
    VoiceGender,
    VoiceLocale,
)
from app.infrastructure.voice.stt.factory import (
    STTFactory,
    get_stt_provider,
    transcribe_audio,
    transcribe_file,
)


def list_stt_providers():
    """获取所有可用 STT 提供商"""
    return STTFactory.list_available_providers()

__all__ = [
    "VoiceGender",
    "VoiceLocale",
    "STTOptions",
    "STTResult",
    "BaseSTTProvider",
    "get_stt_provider",
    "list_stt_providers",
    "transcribe_audio",
    "transcribe_file",
]
