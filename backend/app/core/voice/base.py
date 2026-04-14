"""
Voice Service Base Classes and Models
语音服务基类和数据模型
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import AsyncIterator, Optional
from pydantic import BaseModel, Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class VoiceGender(str, Enum):
    """声音性别"""
    MALE = "male"
    FEMALE = "female"
    NEUTRAL = "neutral"


class VoiceLocale(str, Enum):
    """语言区域"""
    ZH_CN = "zh-CN"    # 简体中文
    ZH_TW = "zh-TW"    # 台湾繁体
    ZH_HK = "zh-HK"    # 香港粤语
    EN_US = "en-US"    # 美式英语
    EN_GB = "en-GB"    # 英式英语
    JA_JP = "ja-JP"    # 日语
    KO_KR = "ko-KR"    # 韩语
    AUTO = "auto"      # 自动检测


class Voice(DynamicBaseModel):
    """声音定义"""
    id: str
    name: str
    gender: VoiceGender
    description: str
    locale: VoiceLocale
    provider: str
    preview_text: str | None = None
    is_streaming: bool = True
    supports_speed: bool = True


class TTSOptions(DynamicBaseModel):
    """TTS 合成选项"""
    text: str
    voice_id: str
    speed: float = 1.0           # 0.5 - 2.0
    pitch: float = 0.0           # 音调调整（部分支持）
    volume: float = 1.0          # 音量（部分支持）
    format: str = "mp3"          # mp3, wav, opus, aac
    locale: VoiceLocale | None = None


class TTSSResult(DynamicBaseModel):
    """TTS 合成结果"""
    audio_data: bytes
    content_type: str
    duration_ms: int | None = None
    sample_rate: int | None = None


class STTOptions(DynamicBaseModel):
    """STT 识别选项"""
    audio_data: bytes
    audio_format: str = "webm"   # webm, mp3, wav, m4a
    language: VoiceLocale = VoiceLocale.AUTO
    model: str | None = None   # 模型选择
    prompt: str | None = None  # 提示词（热词等）
    timestamp_granularities: list | None = None


class STTResult(DynamicBaseModel):
    """STT 识别结果"""
    text: str
    language: VoiceLocale
    duration_ms: int | None = None
    confidence: float | None = None
    words: list | None = None  # 词级别时间戳


class BaseTTSProvider(ABC):
    """TTS 提供商基类"""
    
    name: str = "base"
    supports_streaming: bool = False
    supports_speed_control: bool = False
    
    @abstractmethod
    async def synthesize(self, options: TTSOptions) -> TTSSResult:
        """
        合成语音
        
        Args:
            options: TTS 选项
            
        Returns:
            TTSSResult: 合成的音频数据
        """
        pass
    
    @abstractmethod
    async def synthesize_stream(self, options: TTSOptions) -> AsyncIterator[bytes]:
        """
        流式合成语音（如果支持）
        
        Args:
            options: TTS 选项
            
        Yields:
            bytes: 音频数据块
        """
        pass
    
    @abstractmethod
    def list_voices(self, locale: Optional[VoiceLocale] = None) -> list[Voice]:
        """
        获取可用声音列表
        
        Args:
            locale: 按语言区域过滤
            
        Returns:
            list[Voice]: 声音列表
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        检查提供商是否可用（配置是否正确）
        
        Returns:
            bool: 是否可用
        """
        pass
    
    def get_default_voice(self, locale: VoiceLocale = VoiceLocale.ZH_CN) -> str:
        """
        获取默认声音 ID
        
        Args:
            locale: 语言区域
            
        Returns:
            str: 默认声音 ID
        """
        voices = self.list_voices(locale)
        if voices:
            return voices[0].id
        raise ValueError(f"No voice available for locale {locale}")


class BaseSTTProvider(ABC):
    """STT 提供商基类"""
    
    name: str = "base"
    supports_streaming: bool = False
    supports_timestamps: bool = False
    
    @abstractmethod
    async def transcribe(self, options: STTOptions) -> STTResult:
        """
        识别语音
        
        Args:
            options: STT 选项
            
        Returns:
            STTResult: 识别结果
        """
        pass
    
    @abstractmethod
    async def transcribe_stream(self, options: STTOptions) -> AsyncIterator[STTResult]:
        """
        流式识别语音（如果支持）
        
        Args:
            options: STT 选项
            
        Yields:
            STTResult: 部分识别结果
        """
        pass
    
    @abstractmethod
    def list_models(self, language: Optional[VoiceLocale] = None) -> list[str]:
        """
        获取可用模型列表
        
        Args:
            language: 按语言过滤
            
        Returns:
            list[str]: 模型名称列表
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        检查提供商是否可用
        
        Returns:
            bool: 是否可用
        """
        pass
