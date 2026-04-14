"""
STT Provider Factory
语音识别提供商工厂

支持:
- FunASR (本地，中文优化，推荐)
- OpenAI Whisper (云端，备选)
"""

import logging
from typing import Optional

from app.core.voice.stt.base import BaseSTTProvider, STTOptions, STTResult, VoiceLocale
from app.core.voice.stt.funasr import FunASRProvider, FunASRManager

logger = logging.getLogger(__name__)


class STTFactory:
    """STT 提供商工厂"""
    
    _funasr_provider: Optional[FunASRProvider] = None
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
                return cls.get_funasr_provider()
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
        if cls._funasr_provider is None:
            cls._funasr_provider = FunASRProvider(model_name)
            logger.info(f"FunASR provider initialized: {model_name}")
        return cls._funasr_provider
    
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


async def transcribe_audio(audio_data: bytes, language: Optional[str] = None, **kwargs) -> STTResult:
    """
    便捷函数：识别音频
    
    Args:
        audio_data: 音频数据
        language: 语言代码
        **kwargs: 其他选项
        
    Returns:
        STTResult: 识别结果
    """

    provider = get_stt_provider()
    
    # 转换语言代码
    locale = VoiceLocale.AUTO
    if language:
        lang_map = {
            "zh": VoiceLocale.ZH_CN,
            "zh-CN": VoiceLocale.ZH_CN,
            "en": VoiceLocale.EN_US,
            "en-US": VoiceLocale.EN_US,
            "ja": VoiceLocale.JA_JP,
            "ko": VoiceLocale.KO_KR,
        }
        locale = lang_map.get(language, VoiceLocale.AUTO)
    
    options = STTOptions(
        audio_data=audio_data,
        audio_format=kwargs.get("format", "webm"),
        language=locale,
        prompt=kwargs.get("prompt"),
    )
    
    return await provider.transcribe(options)
