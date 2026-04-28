"""
System TTS Provider (macOS say command)
使用系统自带语音合成（无需联网，无需额外依赖）

支持的语音：
- Tingting (zh_CN) - 婷婷，女声
- Meijia (zh_TW) - 美佳，女声  
- Sinji (zh_HK) - 善怡，女声
- Eddy, Flo, Grandma, Grandpa, Reed, Rocko, Sandy, Shelley
"""

import asyncio
import logging
import os
import tempfile
from collections.abc import AsyncIterator

from app.core.voice.tts.base import (
    BaseTTSProvider,
    TTSOptions,
    TTSSResult,
    Voice,
    VoiceGender,
    VoiceLocale,
)

logger = logging.getLogger(__name__)


# macOS 系统语音定义
MACOS_VOICES = {
    # 中文（大陆）
    "zh-CN-Tingting": {"name": "婷婷", "gender": VoiceGender.FEMALE, "description": "温柔女声", "locale": VoiceLocale.ZH_CN, "voice_id": "Ting-Ting"},
    "zh-CN-Eddy": {"name": "Eddy", "gender": VoiceGender.MALE, "description": "年轻男声", "locale": VoiceLocale.ZH_CN, "voice_id": "Eddy"},
    "zh-CN-Flo": {"name": "Flo", "gender": VoiceGender.FEMALE, "description": "活泼女声", "locale": VoiceLocale.ZH_CN, "voice_id": "Flo"},
    "zh-CN-Grandma": {"name": "奶奶", "gender": VoiceGender.FEMALE, "description": "年长女声", "locale": VoiceLocale.ZH_CN, "voice_id": "Grandma"},
    "zh-CN-Grandpa": {"name": "爷爷", "gender": VoiceGender.MALE, "description": "年长男声", "locale": VoiceLocale.ZH_CN, "voice_id": "Grandpa"},
    "zh-CN-Reed": {"name": "Reed", "gender": VoiceGender.MALE, "description": "成熟男声", "locale": VoiceLocale.ZH_CN, "voice_id": "Reed"},
    "zh-CN-Rocko": {"name": "Rocko", "gender": VoiceGender.MALE, "description": "稳重男声", "locale": VoiceLocale.ZH_CN, "voice_id": "Rocko"},
    "zh-CN-Sandy": {"name": "Sandy", "gender": VoiceGender.FEMALE, "description": "甜美女声", "locale": VoiceLocale.ZH_CN, "voice_id": "Sandy"},
    "zh-CN-Shelley": {"name": "Shelley", "gender": VoiceGender.FEMALE, "description": "清晰女声", "locale": VoiceLocale.ZH_CN, "voice_id": "Shelley"},
    # 中文（台湾）
    "zh-TW-Meijia": {"name": "美佳", "gender": VoiceGender.FEMALE, "description": "台湾女声", "locale": VoiceLocale.ZH_TW, "voice_id": "Meijia"},
    # 中文（香港）
    "zh-HK-Sinji": {"name": "善怡", "gender": VoiceGender.FEMALE, "description": "粤语女声", "locale": VoiceLocale.ZH_HK, "voice_id": "Sinji"},
    # 英文
    "en-US-Samantha": {"name": "Samantha", "gender": VoiceGender.FEMALE, "description": "美式女声", "locale": VoiceLocale.EN_US, "voice_id": "Samantha"},
    "en-US-Alex": {"name": "Alex", "gender": VoiceGender.MALE, "description": "美式男声", "locale": VoiceLocale.EN_US, "voice_id": "Alex"},
    "en-GB-Daniel": {"name": "Daniel", "gender": VoiceGender.MALE, "description": "英式男声", "locale": VoiceLocale.EN_GB, "voice_id": "Daniel"},
    "en-GB-Kate": {"name": "Kate", "gender": VoiceGender.FEMALE, "description": "英式女声", "locale": VoiceLocale.EN_GB, "voice_id": "Kate"},
    # 日文
    "ja-JP-Kyoko": {"name": "Kyoko", "gender": VoiceGender.FEMALE, "description": "日语女声", "locale": VoiceLocale.JA_JP, "voice_id": "Kyoko"},
    # 韩文
    "ko-KR-Yuna": {"name": "Yuna", "gender": VoiceGender.FEMALE, "description": "韩语女声", "locale": VoiceLocale.KO_KR, "voice_id": "Yuna"},
}


class SystemTTSProvider(BaseTTSProvider):
    """
    系统语音合成提供商 (macOS say 命令)
    
    特点：
    - 完全离线，无需网络
    - 无需安装额外依赖
    - 使用 macOS 自带语音
    - 支持多种语言
    """

    name = "system-tts"
    supports_streaming = False
    supports_speed_control = True

    def __init__(self):
        self._is_macos = self._check_macos()

    def _check_macos(self) -> bool:
        """检查是否为 macOS 系统"""
        import platform
        return platform.system() == "Darwin"

    def is_available(self) -> bool:
        """检查系统 TTS 是否可用"""
        if not self._is_macos:
            return False

        # 检查 say 命令是否存在
        try:
            import subprocess
            result = subprocess.run(['which', 'say'], capture_output=True, text=True)
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def list_voices(self, locale: VoiceLocale | None = None) -> list[Voice]:
        """获取可用声音列表"""
        voices = []
        for voice_id, info in MACOS_VOICES.items():
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
            VoiceLocale.ZH_CN: "zh-CN-Tingting",
            VoiceLocale.ZH_TW: "zh-TW-Meijia",
            VoiceLocale.ZH_HK: "zh-HK-Sinji",
            VoiceLocale.EN_US: "en-US-Samantha",
            VoiceLocale.EN_GB: "en-GB-Kate",
            VoiceLocale.JA_JP: "ja-JP-Kyoko",
            VoiceLocale.KO_KR: "ko-KR-Yuna",
        }
        return defaults.get(locale, "zh-CN-Tingting")

    async def synthesize(self, options: TTSOptions) -> TTSSResult:
        """
        合成语音
        
        使用 macOS say 命令生成音频，然后转换为 MP3
        """
        if not self.is_available():
            raise RuntimeError("System TTS not available. This provider only works on macOS.")

        import subprocess

        from app.core.voice.utils import optimize_for_tts

        # 清理 Markdown 格式
        text = optimize_for_tts(options.text)
        if not text or not text.strip():
            logger.warning("TTS synthesis skipped: text is empty after processing")
            # Return empty result instead of raising error
            return TTSSResult(
                audio_data=b"",
                content_type="audio/mpeg",
                duration_ms=0,
                char_count=0,
            )

        # 获取声音 ID
        voice_id = options.voice_id
        if voice_id not in MACOS_VOICES:
            logger.warning(f"Unknown voice {voice_id}, using default")
            voice_id = self.get_default_voice(options.locale or VoiceLocale.ZH_CN)

        macos_voice = MACOS_VOICES[voice_id]["voice_id"]

        # 转换语速 (0.5 - 2.0) 到 macOS 速率 (0 - 100)
        # say 命令的 -r 参数是 words per minute, 默认约 180
        # 我们将 speed 映射到 100 - 300 wpm
        base_rate = 180
        rate = int(base_rate * options.speed)
        rate = max(100, min(300, rate))  # 限制在 100-300

        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix='.aiff', delete=False) as temp_aiff:
            temp_aiff_path = temp_aiff.name

        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_mp3:
            temp_mp3_path = temp_mp3.name

        try:
            # 使用 say 命令生成 AIFF 音频
            cmd = ['say', '-v', macos_voice, '-r', str(rate), '-o', temp_aiff_path, text]

            # 在线程池中执行（避免阻塞）
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, check=True, capture_output=True)
            )

            # 转换为 MP3（使用 afconvert 或 ffmpeg）
            # 使用 MPG3 格式生成真正的 MP3 文件
            convert_cmd = ['afconvert', '-f', 'MPG3', '-d', '.mp3', temp_aiff_path, temp_mp3_path]

            try:
                await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(convert_cmd, check=True, capture_output=True)
                )
            except subprocess.CalledProcessError:
                # 如果 afconvert 失败，尝试使用 ffmpeg
                try:
                    ffmpeg_cmd = ['ffmpeg', '-i', temp_aiff_path, '-codec:a', 'libmp3lame', '-q:a', '2', temp_mp3_path, '-y']
                    await loop.run_in_executor(
                        None,
                        lambda: subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
                    )
                except subprocess.CalledProcessError:
                    # 如果都失败，直接读取 AIFF 文件
                    temp_mp3_path = temp_aiff_path

            # 读取音频数据
            with open(temp_mp3_path, 'rb') as f:
                audio_data = f.read()

            logger.info(f"System TTS synthesized: {len(audio_data)} bytes, voice={voice_id}, rate={rate}")

            return TTSSResult(
                audio_data=audio_data,
                content_type="audio/mpeg",
                duration_ms=None,  # macOS say 不返回时长
                sample_rate=22050  # 系统语音默认采样率
            )

        except subprocess.CalledProcessError as e:
            logger.error(f"System TTS synthesis failed: {e}")
            raise RuntimeError(f"TTS synthesis failed: {e}")
        finally:
            # 清理临时文件
            try:
                if os.path.exists(temp_aiff_path):
                    os.unlink(temp_aiff_path)
                if temp_mp3_path != temp_aiff_path and os.path.exists(temp_mp3_path):
                    os.unlink(temp_mp3_path)
            except OSError:
                pass

    async def synthesize_stream(self, options: TTSOptions) -> AsyncIterator[bytes]:
        """
        流式合成语音（模拟流式）
        """
        result = await self.synthesize(options)

        # 分块返回，模拟流式
        chunk_size = 8192
        for i in range(0, len(result.audio_data), chunk_size):
            yield result.audio_data[i:i + chunk_size]
