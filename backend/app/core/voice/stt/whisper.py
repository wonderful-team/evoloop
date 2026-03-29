"""
OpenAI Whisper STT Provider
OpenAI Whisper 语音识别（云端）
"""

import logging
from typing import Optional, AsyncIterator

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from app.core.config import settings
from app.core.voice.stt.base import BaseSTTProvider, STTOptions, STTResult, VoiceLocale

logger = logging.getLogger(__name__)


class WhisperProvider(BaseSTTProvider):
    """
    OpenAI Whisper 语音识别提供商
    
    使用 OpenAI Whisper API，支持多种语言，需要 API Key。
    """
    
    name = "openai-whisper"
    supports_streaming = False
    supports_timestamps = False
    
    # 支持的模型
    MODELS = {
        "whisper-1": {"description": "通用模型，多语言支持", "language": "multilingual"},
        "whisper-large-v3": {"description": "高精度模型", "language": "multilingual"},
    }
    
    def __init__(self):
        self._client = None
    
    def _get_client(self):
        """获取或创建 OpenAI 客户端"""
        if not self._client:
            api_key = settings.OPENAI_API_KEY
            if not api_key or api_key == "sk-dummy-key-for-local-dev":
                raise RuntimeError("OpenAI API key not configured")
            self._client = openai.AsyncOpenAI(api_key=api_key)
        return self._client
    
    def is_available(self) -> bool:
        """检查 Whisper 是否可用"""
        if not OPENAI_AVAILABLE:
            return False
        api_key = settings.OPENAI_API_KEY
        return api_key is not None and api_key != "sk-dummy-key-for-local-dev"
    
    def list_models(self, language: Optional[VoiceLocale] = None) -> list[str]:
        """获取可用模型列表"""
        return list(self.MODELS.keys())
    
    async def transcribe(self, options: STTOptions) -> STTResult:
        """
        识别语音
        
        Args:
            options: STT 选项
            
        Returns:
            STTResult: 识别结果
        """
        if not OPENAI_AVAILABLE:
            raise RuntimeError("OpenAI not installed")
        
        client = self._get_client()
        
        # 语言映射
        language_code = self._locale_to_code(options.language)
        
        # 模型选择
        model = options.model or "whisper-1"
        if model not in self.MODELS:
            model = "whisper-1"
        
        try:
            # 准备参数
            kwargs = {
                "model": model,
                "file": ("audio.webm", options.audio_data),
                "response_format": "verbose_json",
            }
            
            if language_code and language_code != "auto":
                kwargs["language"] = language_code
            
            if options.prompt:
                kwargs["prompt"] = options.prompt
            
            # 调用 API
            response = await client.audio.transcriptions.create(**kwargs)
            
            # 解析结果
            detected_language = self._code_to_locale(
                getattr(response, 'language', language_code or 'zh')
            )
            
            return STTResult(
                text=response.text,
                language=detected_language,
                duration_ms=getattr(response, 'duration', None),
                confidence=getattr(response, 'confidence', None)
            )
            
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            raise RuntimeError(f"Transcription failed: {e}")
    
    async def transcribe_stream(self, options: STTOptions) -> AsyncIterator[STTResult]:
        """
        流式识别（Whisper 不支持真正的流式，模拟返回）
        """
        result = await self.transcribe(options)
        yield result
    
    def _locale_to_code(self, locale: VoiceLocale) -> Optional[str]:
        """将 VoiceLocale 转换为 Whisper 语言代码"""
        mapping = {
            VoiceLocale.ZH_CN: "zh",
            VoiceLocale.ZH_TW: "zh",
            VoiceLocale.ZH_HK: "zh",
            VoiceLocale.EN_US: "en",
            VoiceLocale.EN_GB: "en",
            VoiceLocale.JA_JP: "ja",
            VoiceLocale.KO_KR: "ko",
            VoiceLocale.AUTO: None,
        }
        return mapping.get(locale)
    
    def _code_to_locale(self, code: str) -> VoiceLocale:
        """将语言代码转换为 VoiceLocale"""
        mapping = {
            "zh": VoiceLocale.ZH_CN,
            "en": VoiceLocale.EN_US,
            "ja": VoiceLocale.JA_JP,
            "ko": VoiceLocale.KO_KR,
        }
        return mapping.get(code, VoiceLocale.AUTO)


class WhisperLocalProvider(BaseSTTProvider):
    """
    本地 Whisper 提供商（使用 faster-whisper 或 whisper.cpp）
    
    TODO: 待实现
    """
    
    name = "whisper-local"
    supports_streaming = False
    supports_timestamps = True
    
    def is_available(self) -> bool:
        return False  # 尚未实现
    
    def list_models(self, language: Optional[VoiceLocale] = None) -> list[str]:
        return ["tiny", "base", "small", "medium", "large-v3"]
    
    async def transcribe(self, options: STTOptions) -> STTResult:
        raise NotImplementedError("Local Whisper not implemented yet")
    
    async def transcribe_stream(self, options: STTOptions) -> AsyncIterator[STTResult]:
        raise NotImplementedError("Local Whisper not implemented yet")
