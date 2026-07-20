"""
Kokoro TTS Provider

Local TTS using the Kokoro-82M model.
Fast CPU inference, 4 Chinese female voices.
"""

import asyncio
import io
import logging
from typing import Any

import soundfile as sf

from app.infrastructure.voice.tts.base import BaseTTSProvider, TTSOptions, TTSResult

logger = logging.getLogger(__name__)

_KOKORO_AVAILABLE = False
try:
    from kokoro import KPipeline
    _KOKORO_AVAILABLE = True
except ImportError:
    logger.warning("[KokoroTTS] kokoro package not available")


class KokoroTTSProvider(BaseTTSProvider):
    name = "kokoro"

    def __init__(self):
        self._pipeline: Any = None
        self._load_lock = asyncio.Lock()

    def is_available(self) -> bool:
        return _KOKORO_AVAILABLE

    def list_voices(self) -> list[str]:
        return ["zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi"]

    async def load_model(self) -> None:
        if self._pipeline is not None:
            return
        async with self._load_lock:
            if self._pipeline is not None:
                return
            logger.info("[KokoroTTS] Loading model ...")
            loop = asyncio.get_running_loop()

            def _load():
                return KPipeline(lang_code='z')

            self._pipeline = await loop.run_in_executor(None, _load)
            logger.info("[KokoroTTS] Model loaded")

    async def generate(self, options: TTSOptions) -> TTSResult:
        await self.load_model()
        loop = asyncio.get_running_loop()
        text, voice = options.text, options.voice

        def _infer():
            gen = self._pipeline(text, voice=voice, speed=1.0)
            chunks = []
            for gs, ps, audio in gen:
                chunks.append(audio)
            if not chunks:
                raise RuntimeError("Kokoro inference produced no audio")
            import numpy as np
            return np.concatenate(chunks) if len(chunks) > 1 else chunks[0]

        audio = await loop.run_in_executor(None, _infer)
        buf = io.BytesIO()
        sf.write(buf, audio, 24000, format="wav")
        return TTSResult(audio_bytes=buf.getvalue(), sample_rate=24000)
