"""
CosyVoice TTS Provider

Local TTS inference using FunAudioLLM/CosyVoice models.
"""

import asyncio
import io
import logging
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import torch

from app.infrastructure.voice.tts.base import BaseTTSProvider, TTSOptions, TTSResult

logger = logging.getLogger(__name__)

DEFAULT_MODEL_DIR = os.path.expanduser("~/.evoloop/models/cosyvoice-300m-instruct")

# Add CosyVoice source to path if available
_COSYVOICE_SRC = os.path.expanduser("~/.evoloop/CosyVoice")
if os.path.isdir(_COSYVOICE_SRC):
    sys.path.insert(0, _COSYVOICE_SRC)

_COSYVOICE_AVAILABLE = False
try:
    from cosyvoice.cli.cosyvoice import AutoModel
    _COSYVOICE_AVAILABLE = True
except ImportError:
    logger.warning("[CosyVoiceTTS] cosyvoice package not available at %s", _COSYVOICE_SRC)


class CosyVoiceTTSProvider(BaseTTSProvider):
    name = "cosyvoice"

    def __init__(self, model_dir: str | None = None):
        self.model_dir = Path(model_dir or DEFAULT_MODEL_DIR)
        self._model: Any = None
        self._load_lock = asyncio.Lock()

    def is_available(self) -> bool:
        if not _COSYVOICE_AVAILABLE:
            return False
        return (self.model_dir / "model.pt").exists()

    def list_voices(self) -> list[str]:
        if self._model is not None:
            return self._model.list_available_spks()
        return ["中文女"]

    async def load_model(self) -> None:
        if self._model is not None:
            return
        async with self._load_lock:
            if self._model is not None:
                return
            logger.info("[CosyVoiceTTS] Loading model from %s ...", self.model_dir)
            loop = asyncio.get_running_loop()

            model_dir = str(self.model_dir)
            def _load():
                model = AutoModel(model_dir=model_dir, fp16=True)
                logger.info("[CosyVoiceTTS] Model loaded (fp16={})".format(torch.backends.mps.is_available() or torch.cuda.is_available()))
                return model

            self._model = await loop.run_in_executor(None, _load)

    async def generate(self, options: TTSOptions) -> TTSResult:
        await self.load_model()
        loop = asyncio.get_running_loop()
        text, voice = options.text, options.voice

        def _infer():
            gen = self._model.inference_sft(text, voice, stream=True)
            chunks = []
            for chunk in gen:
                audio = chunk.get("tts_speech", chunk.get("audio"))
                if audio is not None:
                    chunks.append(audio.cpu() if hasattr(audio, 'cpu') else audio)
            if not chunks:
                raise RuntimeError("CosyVoice inference produced no audio")
            return torch.cat(chunks, dim=-1) if len(chunks) > 1 else chunks[0]

        audio = await loop.run_in_executor(None, _infer)
        if hasattr(audio, 'cpu'):
            audio = audio.cpu().numpy()
        if audio.ndim == 1:
            audio = audio[None, :]
        buf = io.BytesIO()
        sf.write(buf, audio.T, self._model.sample_rate, format="wav")
        return TTSResult(audio_bytes=buf.getvalue(), sample_rate=self._model.sample_rate)

