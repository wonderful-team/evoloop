"""
Edge-TTS Provider Implementation
微软 Edge 浏览器语音合成（免费，无需 API Key）
"""

import logging
from collections.abc import AsyncIterator

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

from app.core.voice.tts.base import (
    BaseTTSProvider,
    TTSOptions,
    TTSSResult,
    Voice,
    VoiceGender,
    VoiceLocale,
)
from app.core.voice.utils import optimize_for_tts

logger = logging.getLogger(__name__)


# Edge-TTS 声音定义
EDGE_TTS_VOICES = {
    # 中文（普通话）
    "zh-CN-XiaoxiaoNeural": {"name": "晓晓", "gender": VoiceGender.FEMALE, "description": "温柔自然，最推荐", "locale": VoiceLocale.ZH_CN},
    "zh-CN-XiaoyiNeural": {"name": "小艺", "gender": VoiceGender.FEMALE, "description": "活泼年轻", "locale": VoiceLocale.ZH_CN},
    "zh-CN-YunxiNeural": {"name": "云希", "gender": VoiceGender.MALE, "description": "年轻阳光，最推荐", "locale": VoiceLocale.ZH_CN},
    "zh-CN-YunjianNeural": {"name": "云健", "gender": VoiceGender.MALE, "description": "新闻播报风格", "locale": VoiceLocale.ZH_CN},
    "zh-CN-YunyangNeural": {"name": "云扬", "gender": VoiceGender.MALE, "description": "沉稳磁性", "locale": VoiceLocale.ZH_CN},
    "zh-CN-YunxiaNeural": {"name": "云霞", "gender": VoiceGender.FEMALE, "description": "成熟稳重", "locale": VoiceLocale.ZH_CN},
    "zh-CN-XiaochenNeural": {"name": "小晨", "gender": VoiceGender.FEMALE, "description": "清新自然", "locale": VoiceLocale.ZH_CN},
    "zh-CN-XiaohanNeural": {"name": "小涵", "gender": VoiceGender.FEMALE, "description": "甜美可爱", "locale": VoiceLocale.ZH_CN},
    # 台湾
    "zh-TW-HsiaoChenNeural": {"name": "晓晨", "gender": VoiceGender.FEMALE, "description": "台湾女声", "locale": VoiceLocale.ZH_TW},
    "zh-TW-YunJheNeural": {"name": "云哲", "gender": VoiceGender.MALE, "description": "台湾男声", "locale": VoiceLocale.ZH_TW},
    # 香港
    "zh-HK-HiuMaanNeural": {"name": "晓曼", "gender": VoiceGender.FEMALE, "description": "香港粤语女声", "locale": VoiceLocale.ZH_HK},
    "zh-HK-WanLungNeural": {"name": "云龙", "gender": VoiceGender.MALE, "description": "香港粤语男声", "locale": VoiceLocale.ZH_HK},
    # 英文
    "en-US-AriaNeural": {"name": "Aria", "gender": VoiceGender.FEMALE, "description": "美式英语女声", "locale": VoiceLocale.EN_US},
    "en-US-GuyNeural": {"name": "Guy", "gender": VoiceGender.MALE, "description": "美式英语男声", "locale": VoiceLocale.EN_US},
    "en-US-JennyNeural": {"name": "Jenny", "gender": VoiceGender.FEMALE, "description": "美式英语女声（标准）", "locale": VoiceLocale.EN_US},
    "en-GB-SoniaNeural": {"name": "Sonia", "gender": VoiceGender.FEMALE, "description": "英式英语女声", "locale": VoiceLocale.EN_GB},
    "en-GB-RyanNeural": {"name": "Ryan", "gender": VoiceGender.MALE, "description": "英式英语男声", "locale": VoiceLocale.EN_GB},
    # 日文
    "ja-JP-NanamiNeural": {"name": "七海", "gender": VoiceGender.FEMALE, "description": "日语女声", "locale": VoiceLocale.JA_JP},
    "ja-JP-KeitaNeural": {"name": "圭太", "gender": VoiceGender.MALE, "description": "日语男声", "locale": VoiceLocale.JA_JP},
    # 韩文
    "ko-KR-SunHiNeural": {"name": "선희", "gender": VoiceGender.FEMALE, "description": "韩语女声", "locale": VoiceLocale.KO_KR},
    "ko-KR-InJoonNeural": {"name": "인준", "gender": VoiceGender.MALE, "description": "韩语男声", "locale": VoiceLocale.KO_KR},
}


class EdgeTTSProvider(BaseTTSProvider):
    """
    Edge-TTS 提供商
    
    使用微软 Edge 浏览器的语音合成服务，完全免费，无需 API Key。
    支持多种语言和声音，中文效果极佳。
    """

    name = "edge-tts"
    supports_streaming = False  # Edge-TTS 不支持真正的流式，需要完整合成
    supports_speed_control = True

    def __init__(self):
        self._voices = None

    def is_available(self) -> bool:
        """检查 Edge-TTS 是否可用"""
        return EDGE_TTS_AVAILABLE

    def list_voices(self, locale: VoiceLocale | None = None) -> list[Voice]:
        """
        获取可用声音列表
        
        Args:
            locale: 按语言区域过滤，None 返回所有
            
        Returns:
            list[Voice]: 声音列表
        """
        voices = []
        for voice_id, info in EDGE_TTS_VOICES.items():
            if locale and info["locale"] != locale:
                continue

            voices.append(Voice(
                id=voice_id,
                name=info["name"],
                gender=info["gender"],
                description=info["description"],
                locale=info["locale"],
                provider=self.name,
                preview_text=f"你好，我是{info['name']}。" if info["locale"].startswith("zh") else f"Hello, I'm {info['name']}.",
                is_streaming=False,
                supports_speed=True
            ))

        return voices

    def get_default_voice(self, locale: VoiceLocale = VoiceLocale.ZH_CN) -> str:
        """获取默认声音 ID"""
        defaults = {
            VoiceLocale.ZH_CN: "zh-CN-XiaoxiaoNeural",
            VoiceLocale.ZH_TW: "zh-TW-HsiaoChenNeural",
            VoiceLocale.ZH_HK: "zh-HK-HiuMaanNeural",
            VoiceLocale.EN_US: "en-US-AriaNeural",
            VoiceLocale.EN_GB: "en-GB-SoniaNeural",
            VoiceLocale.JA_JP: "ja-JP-NanamiNeural",
            VoiceLocale.KO_KR: "ko-KR-SunHiNeural",
        }
        return defaults.get(locale, "zh-CN-XiaoxiaoNeural")

    async def synthesize(self, options: TTSOptions) -> TTSSResult:
        """
        合成语音
        
        Args:
            options: TTS 选项
            
        Returns:
            TTSSResult: 合成的音频数据
        """
        if not EDGE_TTS_AVAILABLE:
            raise RuntimeError("Edge-TTS not installed. Run: pip install edge-tts")

        # 验证声音 ID
        voice_id = options.voice_id
        if voice_id not in EDGE_TTS_VOICES:
            logger.warning(f"Unknown voice {voice_id}, using default")
            voice_id = self.get_default_voice(options.locale or VoiceLocale.ZH_CN)

        # 清理 Markdown 格式，优化文本
        text = optimize_for_tts(options.text)
        if not text.strip():
            raise RuntimeError("Text is empty after processing")

        # 转换语速为 Edge-TTS 格式
        # Edge-TTS rate: -50% to +50%，对应 0.5x - 1.5x 速度
        rate_percent = int((options.speed - 1.0) * 100)
        rate_str = f"{max(-50, min(50, rate_percent)):+d}%"

        try:
            communicate = edge_tts.Communicate(
                text,
                voice_id,
                rate=rate_str
            )

            # 收集所有音频数据
            audio_chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])

            audio_data = b"".join(audio_chunks)

            return TTSSResult(
                audio_data=audio_data,
                content_type="audio/mpeg",
                duration_ms=None,  # Edge-TTS 不返回时长
                sample_rate=24000  # Edge-TTS 默认 24kHz
            )

        except Exception as e:
            logger.error(f"Edge-TTS synthesis failed: {e}")
            raise RuntimeError(f"TTS synthesis failed: {e}")

    async def synthesize_stream(self, options: TTSOptions) -> AsyncIterator[bytes]:
        """
        流式合成语音（模拟流式，实际 Edge-TTS 不支持真正的流式）
        
        为了兼容接口，边合成边返回
        
        Args:
            options: TTS 选项
            
        Yields:
            bytes: 音频数据块
        """
        if not EDGE_TTS_AVAILABLE:
            raise RuntimeError("Edge-TTS not installed")

        # 验证声音 ID
        voice_id = options.voice_id
        if voice_id not in EDGE_TTS_VOICES:
            logger.warning(f"Unknown voice {voice_id}, using default")
            voice_id = self.get_default_voice(options.locale or VoiceLocale.ZH_CN)

        # 清理 Markdown 格式，优化文本
        text = optimize_for_tts(options.text)
        if not text.strip():
            raise RuntimeError("Text is empty after processing")

        # 转换语速
        rate_percent = int((options.speed - 1.0) * 100)
        rate_str = f"{max(-50, min(50, rate_percent)):+d}%"

        try:
            communicate = edge_tts.Communicate(
                text,
                voice_id,
                rate=rate_str
            )

            # 边合成边返回（模拟流式）
            buffer = bytearray()
            buffer_size = 16384  # 16KB 缓冲区

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buffer.extend(chunk["data"])

                    # 缓冲区满时 yield
                    while len(buffer) >= buffer_size:
                        yield bytes(buffer[:buffer_size])
                        buffer = buffer[buffer_size:]

            # 返回剩余数据
            if buffer:
                yield bytes(buffer)

        except Exception as e:
            logger.error(f"Edge-TTS streaming failed: {e}")
            raise RuntimeError(f"TTS streaming failed: {e}")
