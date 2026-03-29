"""
TTS Provider Factory
TTS 提供商工厂

当前只支持 Edge-TTS（免费，无需 API Key）
"""

import logging
from typing import Optional

from app.core.voice.tts.base import BaseTTSProvider, VoiceLocale
from app.core.voice.tts.edge_tts import EdgeTTSProvider
from app.core.voice.tts.system_tts import SystemTTSProvider

logger = logging.getLogger(__name__)

# 注册所有 TTS 提供商（按优先级排序）
_TTS_PROVIDERS = {
    "system-tts": SystemTTSProvider,  # 首选：系统语音（离线）
    "edge-tts": EdgeTTSProvider,      # 备选：Edge-TTS（需联网）
}


class TTSFactory:
    """TTS 提供商工厂"""
    
    _instance: Optional[BaseTTSProvider] = None
    _provider_name: str = ""
    
    @classmethod
    def get_provider(cls, prefer_offline: bool = True) -> BaseTTSProvider:
        """
        获取 TTS 提供商实例
        
        Args:
            prefer_offline: 优先使用离线方案（系统语音）
            
        Returns:
            BaseTTSProvider: TTS 提供商实例
        """
        if cls._instance is not None:
            return cls._instance
        
        # 按优先级尝试各个提供商
        if prefer_offline:
            # 先尝试系统语音（macOS）
            try:
                provider = SystemTTSProvider()
                if provider.is_available():
                    cls._instance = provider
                    cls._provider_name = "system-tts"
                    logger.info("TTS provider initialized: system-tts (offline)")
                    return provider
            except Exception as e:
                logger.warning(f"System TTS not available: {e}")
            
            # 再尝试 Edge-TTS
            try:
                provider = EdgeTTSProvider()
                if provider.is_available():
                    cls._instance = provider
                    cls._provider_name = "edge-tts"
                    logger.info("TTS provider initialized: edge-tts (online)")
                    return provider
            except Exception as e:
                logger.warning(f"Edge-TTS not available: {e}")
        else:
            # 优先使用 Edge-TTS
            try:
                provider = EdgeTTSProvider()
                if provider.is_available():
                    cls._instance = provider
                    cls._provider_name = "edge-tts"
                    logger.info("TTS provider initialized: edge-tts (online)")
                    return provider
            except Exception as e:
                logger.warning(f"Edge-TTS not available: {e}")
            
            # 回退到系统语音
            try:
                provider = SystemTTSProvider()
                if provider.is_available():
                    cls._instance = provider
                    cls._provider_name = "system-tts"
                    logger.info("TTS provider initialized: system-tts (offline)")
                    return provider
            except Exception as e:
                logger.warning(f"System TTS not available: {e}")
        
        raise RuntimeError(
            "No TTS provider available. "
            "On macOS, system voices should be available. "
            "Otherwise, please install: pip install edge-tts"
        )
    
    @classmethod
    def get_provider_for_voice(cls, voice_id: str, prefer_offline: bool = True) -> BaseTTSProvider:
        """
        根据声音 ID 获取提供商
        
        Args:
            voice_id: 声音 ID
            prefer_offline: 优先使用离线方案
            
        Returns:
            BaseTTSProvider: TTS 提供商
        """
        from app.core.voice.tts.edge_tts import EDGE_TTS_VOICES
        from app.core.voice.tts.system_tts import MACOS_VOICES
        
        # 根据 voice_id 选择合适的提供商
        if voice_id in MACOS_VOICES:
            # 系统语音可用
            return cls.get_provider(prefer_offline=True)
        elif voice_id in EDGE_TTS_VOICES:
            # Edge-TTS 语音
            return cls.get_provider(prefer_offline=False)
        else:
            # 未知声音，使用默认提供商
            logger.warning(f"Unknown voice {voice_id}, using default provider")
            return cls.get_provider(prefer_offline)
    
    @classmethod
    def list_all_voices(cls, locale: Optional[VoiceLocale] = None) -> list[dict]:
        """
        获取所有可用声音列表
        
        Args:
            locale: 按语言区域过滤
            
        Returns:
            list[dict]: 所有声音的列表
        """
        voices = []
        
        # 尝试获取所有提供商的声音
        for provider_name, provider_class in _TTS_PROVIDERS.items():
            try:
                provider = provider_class()
                if not provider.is_available():
                    continue
                
                for voice in provider.list_voices(locale):
                    voices.append({
                        "id": voice.id,
                        "name": voice.name,
                        "gender": voice.gender.value,
                        "description": voice.description,
                        "locale": voice.locale.value,
                        "provider": voice.provider,
                        "preview": voice.preview_text,
                        "supports_streaming": voice.is_streaming,
                        "supports_speed": voice.supports_speed,
                    })
            except Exception as e:
                logger.warning(f"Failed to list voices from {provider_name}: {e}")
        
        return voices
    
    @classmethod
    def clear_cache(cls):
        """清除提供商实例缓存"""
        cls._instance = None
        cls._provider_name = ""
        logger.info("TTS provider cache cleared")


# 便捷函数
def get_tts_provider(prefer_offline: bool = True) -> BaseTTSProvider:
    """获取 TTS 提供商实例的便捷函数"""
    return TTSFactory.get_provider(prefer_offline)
