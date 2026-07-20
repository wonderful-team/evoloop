"""
Qwen-TTS Provider (cloud-based, proxies to DashScope API via Rust)
"""

import asyncio
import logging
from typing import Any

from app.infrastructure.voice.tts.base import BaseTTSProvider, TTSOptions, TTSResult

logger = logging.getLogger(__name__)


class QwenTTSProvider(BaseTTSProvider):
    name = "qwen-tts"

    def __init__(self):
        pass

    def is_available(self) -> bool:
        return True

    def list_voices(self) -> list[str]:
        return ["Cherry", "Serena", "Ethan", "Sunny", "Li", "Eric"]

    async def load_model(self) -> None:
        pass

    async def generate(self, options: TTSOptions) -> TTSResult:
        raise NotImplementedError("Qwen-TTS should be called from Rust directly")
