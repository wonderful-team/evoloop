"""
OpenAI Whisper STT Provider
OpenAI Whisper 语音识别（云端）
"""

import logging
import os
from typing import Any
from collections.abc import AsyncIterator

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
            # Whisper provider requires STT_API_KEY to be configured explicitly.
            api_key = getattr(settings, 'STT_API_KEY', None)
            if not api_key:
                raise RuntimeError(
                    "Whisper API key not configured. "
                    "Please set STT_API_KEY in settings or use a local STT provider."
                )
            self._client = openai.AsyncOpenAI(api_key=api_key)
        return self._client

    def is_available(self) -> bool:
        """检查 Whisper 是否可用"""
        if not OPENAI_AVAILABLE:
            return False
        api_key = getattr(settings, 'STT_API_KEY', None)
        return api_key is not None

    def list_models(self, language: VoiceLocale | None = None) -> list[str]:
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
            kwargs: dict[str, Any] = {
                "model": model,
                "response_format": "verbose_json",
            }

            if language_code and language_code != "auto":
                kwargs["language"] = language_code

            if options.prompt:
                kwargs["prompt"] = options.prompt

            # 如果提供了文件路径，使用文件流上传（内存友好）
            if options.file_path and os.path.exists(options.file_path):
                with open(options.file_path, "rb") as audio_file:
                    kwargs["file"] = (os.path.basename(options.file_path), audio_file)
                    response = await client.audio.transcriptions.create(**kwargs)
            else:
                # 否则使用内存数据
                if not options.audio_data:
                    raise ValueError("Either audio_data or file_path must be provided")
                kwargs["file"] = ("audio.webm", options.audio_data)
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

    def transcribe_stream(self, options: STTOptions) -> AsyncIterator[STTResult]:
        """
        流式识别（Whisper 不支持真正的流式，模拟返回）
        """
        async def _gen():
            result = await self.transcribe(options)
            yield result
        return _gen()

    def _locale_to_code(self, locale: VoiceLocale) -> str | None:
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

    def list_models(self, language: VoiceLocale | None = None) -> list[str]:
        return ["tiny", "base", "small", "medium", "large-v3"]

    async def transcribe(self, options: STTOptions) -> STTResult:
        raise NotImplementedError("Local Whisper not implemented yet")

    def transcribe_stream(self, options: STTOptions) -> AsyncIterator[STTResult]:
        raise NotImplementedError("Local Whisper not implemented yet")
