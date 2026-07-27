"""
EvoLoop Voice Module
语音模块 - 提供标准化的语音识别(STT)和语音合成(TTS)服务
"""

import wave
import logging
import asyncio

from app.infrastructure.voice.base import (
    BaseSTTProvider,
    STTOptions,
    STTResult,
    VoiceGender,
    VoiceLocale,
)
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.voice.volc_dialog import VolcDialogClient
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


async def transcribe_file(file_path: str) -> STTResult:
    """利用火山引擎 WebSocket 客户端转录 WAV 音频文件。"""
    app_id = SystemConfigService.get_value("SEEDUPLEX_APP_ID")
    access_key = SystemConfigService.get_value("SEEDUPLEX_ACCESS_KEY")
    if not app_id or not access_key:
        logger.warning("[voice] SEEDUPLEX credentials not configured, cannot transcribe file")
        return STTResult(text="", language=VoiceLocale.ZH_CN)

    client = VolcDialogClient(app_id, access_key, session_id=gen_uuid())
    try:
        await client.connect()
        with wave.open(file_path, 'rb') as wf:
            # Volcengine expects 16kHz 16-bit mono PCM chunks
            chunk_size = 3200
            while True:
                data = wf.readframes(chunk_size)
                if not data:
                    break
                await client.send_audio(data)
                # Brief sleep to avoid flooding
                await asyncio.sleep(0.005)

        # Wait for ASR text response (event 459)
        text = ""
        for _ in range(100):
            resp = await client.receive_response()
            mtype = resp.get("message_type")
            event = resp.get("event")
            payload = resp.get("payload_msg")
            
            if mtype == "SERVER_FULL_RESPONSE" and event == 459:
                if isinstance(payload, dict):
                    text = payload.get("asr_result", "").strip()
                break
        return STTResult(text=text, language=VoiceLocale.ZH_CN)
    except Exception as e:
        logger.error(f"[voice] transcribe_file failed: {e}", exc_info=e)
        return STTResult(text="", language=VoiceLocale.ZH_CN)
    finally:
        await client.close()


def list_stt_providers():
    """获取所有可用 STT 提供商"""
    return ["volcengine"]


__all__ = [
    "VoiceGender",
    "VoiceLocale",
    "STTOptions",
    "STTResult",
    "transcribe_file",
    "list_stt_providers",
]
