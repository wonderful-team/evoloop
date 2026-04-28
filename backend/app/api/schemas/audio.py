"""API schemas for audio routes."""

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.api.schemas.responses import BaseAPIResponse, ListResponse
from typing import Optional
from typing import Any
from typing import Any, Optional

class TranscriptionResponse(BaseAPIResponse):
    """语音识别响应"""
    text: str
    duration: float
    language: str
    confidence: Optional[float] = None

class TTSRequest(DynamicBaseModel):
    """语音合成请求"""
    text: str
    voice_id: str = "zh-CN-XiaoxiaoNeural"  # Edge-TTS 默认声音
    speed: float = 1.0  # 0.5 - 2.0
    format: str = "mp3"  # mp3 (Edge-TTS 只支持 mp3)

class TTSResponse(BaseAPIResponse):
    """语音合成响应"""
    url: str
    duration: Optional[float] = None

class VoiceListResponse(BaseAPIResponse):
    """TTS 声音列表响应"""
    voices: list[dict[str, Any]]

class STTProvidersResponse(BaseAPIResponse):
    """STT 提供商列表响应"""
    providers: list[dict[str, Any]]
