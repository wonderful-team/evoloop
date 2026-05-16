"""
STT Provider Factory
语音识别提供商工厂

支持:
- FunASR (本地，中文优化，推荐)
- OpenAI Whisper (云端，备选)
"""

import logging

from app.core.voice.stt.base import BaseSTTProvider, STTOptions, STTResult, VoiceLocale
from app.core.voice.stt.funasr import FunASRManager, FunASRProvider

logger = logging.getLogger(__name__)


class STTFactory:
    """STT 提供商工厂"""

    _whisper_provider = None  # 延迟导入

    @classmethod
    def get_provider(cls, prefer_local: bool = True) -> BaseSTTProvider:
        """
        获取 STT 提供商
        
        Args:
            prefer_local: 优先使用本地模型 (FunASR)
            
        Returns:
            BaseSTTProvider: STT 提供商实例
        """
        if prefer_local:
            # 尝试 FunASR
            try:
                provider = cls.get_funasr_provider()
                if provider.is_available():
                    return provider
            except Exception as e:
                logger.warning(f"FunASR not available: {e}, falling back to Whisper")

        # 回退到 Whisper
        return cls.get_whisper_provider()

    @classmethod
    def get_funasr_provider(cls, model_name: str = "paraformer-zh") -> FunASRProvider:
        """
        获取 FunASR 提供商
        
        Args:
            model_name: 模型名称，默认 paraformer-zh
            
        Returns:
            FunASRProvider: FunASR 提供商
        """
        return FunASRManager.get_provider(model_name)

    @classmethod
    def get_whisper_provider(cls):
        """
        获取 Whisper 提供商
        
        Returns:
            WhisperProvider: Whisper 提供商
        """
        if cls._whisper_provider is None:
            # 延迟导入，避免依赖问题
            from app.core.voice.stt.whisper import WhisperProvider
            cls._whisper_provider = WhisperProvider()
            logger.info("Whisper provider initialized")
        return cls._whisper_provider

    @classmethod
    def list_available_providers(cls) -> list[dict]:
        """
        获取所有可用的提供商列表
        
        Returns:
            list[dict]: 提供商信息列表
        """
        providers = []

        # 检查 FunASR
        try:
            funasr = FunASRProvider()
            providers.append({
                "name": "funasr",
                "available": funasr.is_available(),
                "description": "本地语音识别，中文优化，免费",
                "models": funasr.list_models(),
            })
        except Exception as e:
            providers.append({
                "name": "funasr",
                "available": False,
                "description": f"不可用: {e}",
            })

        # 检查 Whisper
        try:
            from app.core.voice.stt.whisper import WhisperProvider
            whisper = WhisperProvider()
            providers.append({
                "name": "whisper",
                "available": whisper.is_available(),
                "description": "云端语音识别，需要 OpenAI API Key",
                "models": whisper.list_models(),
            })
        except Exception as e:
            providers.append({
                "name": "whisper",
                "available": False,
                "description": f"不可用: {e}",
            })

        return providers

    @classmethod
    def preload_funasr(cls, model_name: str = "paraformer-zh"):
        """预加载 FunASR 模型"""
        try:
            FunASRManager.preload_model(model_name)
        except Exception as e:
            logger.error(f"Failed to preload FunASR: {e}")

    @classmethod
    def clear_cache(cls):
        """清除缓存"""
        cls._funasr_provider = None
        cls._whisper_provider = None
        FunASRManager.clear_cache()
        logger.info("STT provider cache cleared")


# 便捷函数
def get_stt_provider(prefer_local: bool = True) -> BaseSTTProvider:
    """获取 STT 提供商的便捷函数"""
    return STTFactory.get_provider(prefer_local)


async def transcribe_audio(audio_data: bytes, language: str | None = None, **kwargs) -> STTResult:
    """
    便捷函数：识别音频数据
    """
    provider = get_stt_provider()
    locale = _resolve_locale(language)

    options = STTOptions(
        audio_data=audio_data,
        audio_format=kwargs.get("format", "webm"),
        language=locale,
        prompt=kwargs.get("prompt"),
    )

    return await provider.transcribe(options)


async def transcribe_file(file_path: str, language: str | None = None, **kwargs) -> STTResult:
    """
    便捷函数：识别音频文件
    """
    import os
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")
        
    locale = _resolve_locale(language)
    ext = os.path.splitext(file_path)[1].lstrip(".").lower()
    
    options = STTOptions(
        file_path=file_path,
        audio_format=ext,
        language=locale,
        prompt=kwargs.get("prompt"),
    )
    
    provider = get_stt_provider()
    return await provider.transcribe(options)


def _resolve_locale(language: str | None) -> VoiceLocale:
    """转换语言代码为 VoiceLocale"""
    if not language:
        return VoiceLocale.AUTO
        
    lang_map = {
        "zh": VoiceLocale.ZH_CN,
        "zh-CN": VoiceLocale.ZH_CN,
        "en": VoiceLocale.EN_US,
        "en-US": VoiceLocale.EN_US,
        "ja": VoiceLocale.JA_JP,
        "ko": VoiceLocale.KO_KR,
    }
    return lang_map.get(language, VoiceLocale.AUTO)
