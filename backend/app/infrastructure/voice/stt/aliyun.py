"""
Aliyun DashScope STT Provider
阿里云百炼语音识别（云端）
"""

import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import openai

from app.core.config import settings
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.voice.stt.base import (
    BaseSTTProvider,
    STTOptions,
    STTResult,
    VoiceLocale,
)

logger = logging.getLogger(__name__)


class AliyunProvider(BaseSTTProvider):
    """
    阿里云百炼语音识别提供商

    使用 OpenAI 兼容接口访问通义语音模型（如 qwen-audio-turbo），支持中英混杂，精度极高。
    """

    name = "aliyun-sensevoice"
    supports_streaming = False
    supports_timestamps = False

    # 支持的模型
    MODELS = {
        "qwen-audio-turbo": {
            "description": "通义千问语音大模型，中英混杂极佳",
            "language": "multilingual",
        },
        "paraformer-v1": {
            "description": "高精度中文语音识别",
            "language": "zh"
        },
    }

    def __init__(self):
        self._client = None

    def _get_client(self):
        """获取或创建 OpenAI 兼容的 Aliyun 客户端"""
        if not self._client:
            # 优先从数据库中获取 API Key，如果没有则读取系统配置
            api_key = SystemConfigService.get_value("STT_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "Aliyun API key not configured. "
                    "Please set STT_API_KEY in settings or database."
                )

            # 使用阿里云百炼 OpenAI 兼容端点
            self._client = openai.AsyncOpenAI(
                api_key=api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
        return self._client

    def is_available(self) -> bool:
        """检查 Aliyun STT 是否可用"""
        api_key = SystemConfigService.get_value("STT_API_KEY")
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
        client = self._get_client()

        # 语言映射
        language_code = self._locale_to_code(options.language)

        # 模型选择，默认使用 qwen-audio-turbo，在中文/英文混合场景有顶级精度
        model = options.model or "qwen-audio-turbo"
        if model not in self.MODELS:
            model = "qwen-audio-turbo"

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

            # 上传文件进行识别
            if options.file_path and os.path.exists(options.file_path):
                with open(options.file_path, "rb") as audio_file:
                    kwargs["file"] = (os.path.basename(options.file_path), audio_file)
                    response = await client.audio.transcriptions.create(**kwargs)
            else:
                if not options.audio_data:
                    raise ValueError("Either audio_data or file_path must be provided")
                kwargs["file"] = ("audio.webm", options.audio_data)
                response = await client.audio.transcriptions.create(**kwargs)

            detected_language = self._code_to_locale(
                getattr(response, "language", language_code or "zh")
            )

            return STTResult(
                text=response.text,
                language=detected_language,
                duration_ms=getattr(response, "duration", None),
                confidence=getattr(response, "confidence", None),
            )

        except Exception as e:
            logger.error(f"Aliyun transcription failed: {e}")
            raise RuntimeError(f"Transcription failed: {e}")

    def transcribe_stream(self, options: STTOptions) -> AsyncIterator[STTResult]:
        """
        流式识别
        """

        async def _gen():
            result = await self.transcribe(options)
            yield result

        return _gen()

    def _locale_to_code(self, locale: VoiceLocale) -> str | None:
        """将 VoiceLocale 转换为 Aliyun 语言代码"""
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
