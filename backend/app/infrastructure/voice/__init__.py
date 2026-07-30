"""
EvoLoop Voice Module
语音模块 - 提供标准化的语音识别(STT)和语音合成(TTS)服务

STT 实现已迁移到 app.infrastructure.voice.stt 子包，本文件仅保留
向后兼容的公共 API 导出。
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

__all__ = [
    "VoiceGender",
    "VoiceLocale",
    "STTOptions",
    "STTResult",
    "BaseSTTProvider",
    "STTFactory",
    "get_stt_provider",
    "transcribe_file",
    "transcribe_audio",
]


def list_stt_providers():
    """获取所有 STT 提供商名称（向后兼容）"""
    return [p["name"] for p in STTFactory.list_available_providers()]


def list_available_providers():
    """获取所有 STT 提供商详情"""
    return STTFactory.list_available_providers()
