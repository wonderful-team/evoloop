"""
EvoLoop Voice Module
语音模块 - 提供标准化的语音合成(TTS)和语音识别(STT)服务

使用示例:
    # TTS 合成
    from app.core.voice import get_tts_provider, TTSOptions
    
    provider = get_tts_provider()
    result = await provider.synthesize(TTSOptions(
        text="你好，我是智能语音助手",
        voice_id="zh-CN-XiaoxiaoNeural",
        speed=1.0
    ))
    
    # 获取所有声音
    from app.core.voice import list_all_voices
    voices = list_all_voices()
"""

from app.core.voice.base import (
    Voice,
    VoiceGender,
    VoiceLocale,
    TTSOptions,
    TTSSResult,
    STTOptions,
    STTResult,
    BaseTTSProvider,
    BaseSTTProvider,
)
from app.core.voice.stt.factory import (
    get_stt_provider,
    STTFactory,
    transcribe_audio,
)
from app.core.voice.tts.factory import (
    get_tts_provider,
    TTSFactory,
)


# 便捷函数
def list_tts_voices(locale=None):
    """获取所有可用 TTS 声音"""
    return TTSFactory.list_all_voices(locale)

def list_stt_providers():
    """获取所有可用 STT 提供商"""
    return STTFactory.list_available_providers()

__all__ = [
    # 数据模型
    "Voice",
    "VoiceGender", 
    "VoiceLocale",
    "TTSOptions",
    "TTSSResult",
    "STTOptions",
    "STTResult",
    # 提供商基类
    "BaseTTSProvider",
    "BaseSTTProvider",
    # TTS 便捷函数
    "get_tts_provider",
    "list_tts_voices",
    # STT 便捷函数
    "get_stt_provider",
    "list_stt_providers",
    "transcribe_audio",
]
