"""
STT Provider Factory
语音识别提供商工厂

支持:
- Qwen3-ASR (本地，高精度离线，推荐)
- Aliyun SenseVoice (云端，中英混合推荐)
- OpenAI Whisper (云端，备选)
"""

import logging
import os

from app.infrastructure.voice.stt.base import (
    BaseSTTProvider,
    STTOptions,
    STTResult,
    VoiceLocale,
)
from app.infrastructure.voice.stt.qwen3_asr import Qwen3ASRProvider

logger = logging.getLogger(__name__)


class STTFactory:
    """STT 提供商工厂"""

    _qwen3_provider = None
    _whisper_provider = None  # 延迟导入
    _aliyun_provider = None  # 延迟导入

    @classmethod
    def get_provider(cls, prefer_local: bool = True) -> BaseSTTProvider:
        """
        获取 STT 提供商，读取系统配置数据库中的 STT_PROVIDER

        Args:
            prefer_local: 仅用作向下兼容的备选参数

        Returns:
            BaseSTTProvider: STT 提供商实例
        """
        from app.infrastructure.config.service import SystemConfigService

        provider_name = SystemConfigService.get_value("STT_PROVIDER")

        # 1. 尝试数据库配置的 Provider
        if provider_name in ("qwen3-asr", "qwen3"):
            try:
                provider = cls.get_qwen3_provider()
                if provider.is_available():
                    return provider
            except Exception as e:
                logger.warning(f"Configured STT provider '{provider_name}' not available: {e}, falling back...")
        elif provider_name == "aliyun-sensevoice":
            try:
                provider = cls.get_aliyun_provider()
                if provider.is_available():
                    return provider
            except Exception as e:
                logger.warning(f"Configured STT provider '{provider_name}' not available: {e}, falling back...")
        elif provider_name in ("openai-whisper", "whisper"):
            try:
                provider = cls.get_whisper_provider()
                if provider.is_available():
                    return provider
            except Exception as e:
                logger.warning(f"Configured STT provider '{provider_name}' not available: {e}, falling back...")

        # 2. 备选方案：无配置或配置的 Provider 不可用时，优先回退到 Qwen3-ASR 本地模型
        if prefer_local:
            try:
                provider = cls.get_qwen3_provider()
                if provider.is_available():
                    return provider
            except Exception as e:
                logger.warning(f"Qwen3-ASR fallback not available: {e}")

        # 3. 最终回退到阿里云/Whisper
        try:
            provider = cls.get_aliyun_provider()
            if provider.is_available():
                return provider
        except Exception:
            pass

        return cls.get_whisper_provider()

    @classmethod
    def get_qwen3_provider(cls, model_dir: str | None = None) -> Qwen3ASRProvider:
        """
        获取 Qwen3-ASR 提供商

        Returns:
            Qwen3ASRProvider: Qwen3-ASR 提供商
        """
        if cls._qwen3_provider is None:
            cls._qwen3_provider = Qwen3ASRProvider(model_dir=model_dir)
            logger.info("Qwen3-ASR provider initialized")
        return cls._qwen3_provider

    @classmethod
    def get_aliyun_provider(cls):
        """
        获取阿里云 SenseVoice 提供商

        Returns:
            AliyunProvider: 阿里云 SenseVoice 提供商
        """
        if cls._aliyun_provider is None:
            from app.infrastructure.voice.stt.aliyun import AliyunProvider

            cls._aliyun_provider = AliyunProvider()
            logger.info("Aliyun SenseVoice provider initialized")
        return cls._aliyun_provider

    @classmethod
    def get_whisper_provider(cls):
        """
        获取 Whisper 提供商

        Returns:
            WhisperProvider: Whisper 提供商
        """
        if cls._whisper_provider is None:
            # 延迟导入，避免依赖问题
            from app.infrastructure.voice.stt.whisper import WhisperProvider

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

        # 检查 Qwen3-ASR
        try:
            qwen3 = cls.get_qwen3_provider()
            providers.append({
                "name": "qwen3-asr",
                "available": qwen3.is_available(),
                "description": "本地语音识别，高精度离线，免费",
                "models": qwen3.list_models(),
            })
        except Exception as e:
            providers.append({
                "name": "qwen3-asr",
                "available": False,
                "description": f"不可用: {e}",
            })

        # 检查 Aliyun SenseVoice
        try:
            from app.infrastructure.voice.stt.aliyun import AliyunProvider

            aliyun = AliyunProvider()
            providers.append({
                "name": "aliyun-sensevoice",
                "available": aliyun.is_available(),
                "description": "阿里云百炼语音识别，中英混杂极高，商业推荐",
                "models": aliyun.list_models(),
            })
        except Exception as e:
            providers.append({
                "name": "aliyun-sensevoice",
                "available": False,
                "description": f"不可用: {e}",
            })

        # 检查 Whisper
        try:
            from app.infrastructure.voice.stt.whisper import WhisperProvider

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
    def clear_cache(cls):
        """清除缓存"""
        cls._qwen3_provider = None
        cls._aliyun_provider = None
        cls._whisper_provider = None
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


# 注册配置变更监听器，当配置改变时自动清除 STT 提供商缓存，确保新密钥/配置即时生效
async def _on_stt_config_changed(_old_value: str, _new_value: str) -> None:
    logger.info("STT configuration changed, clearing provider cache...")
    STTFactory.clear_cache()


try:
    from app.infrastructure.config.service import SystemConfigService

    SystemConfigService.register_change_handler("STT_PROVIDER", _on_stt_config_changed)
    SystemConfigService.register_change_handler("STT_API_KEY", _on_stt_config_changed)
    SystemConfigService.register_change_handler("QWEN3_ASR_MODEL_DIR", _on_stt_config_changed)
except Exception as e:
    logger.error(f"Failed to register STT config change handlers: {e}")
