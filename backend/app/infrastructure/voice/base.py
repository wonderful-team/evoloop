"""
Voice Service Base Classes and Models (STT only).
TTS has been migrated to Tauri native. See ``frontend/src-tauri/src/lib.rs``.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from enum import Enum

from app.infrastructure.pydantic_base import DynamicBaseModel


class VoiceGender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    NEUTRAL = "neutral"


class VoiceLocale(str, Enum):
    ZH_CN = "zh-CN"
    ZH_TW = "zh-TW"
    ZH_HK = "zh-HK"
    EN_US = "en-US"
    EN_GB = "en-GB"
    JA_JP = "ja-JP"
    KO_KR = "ko-KR"
    AUTO = "auto"


class STTOptions(DynamicBaseModel):
    audio_data: bytes | None = None
    file_path: str | None = None
    audio_format: str = "webm"
    language: VoiceLocale = VoiceLocale.AUTO
    model: str | None = None
    prompt: str | None = None
    timestamp_granularities: list | None = None


class STTResult(DynamicBaseModel):
    text: str
    language: VoiceLocale
    duration_ms: int | None = None
    confidence: float | None = None
    words: list | None = None


class BaseSTTProvider(ABC):
    name: str = "base"
    supports_streaming: bool = False
    supports_timestamps: bool = False

    @abstractmethod
    async def transcribe(self, options: STTOptions) -> STTResult: ...

    @abstractmethod
    def transcribe_stream(self, options: STTOptions) -> AsyncIterator[STTResult]: ...

    @abstractmethod
    def list_models(self, language: VoiceLocale | None = None) -> list[str]: ...

    @abstractmethod
    def is_available(self) -> bool: ...
