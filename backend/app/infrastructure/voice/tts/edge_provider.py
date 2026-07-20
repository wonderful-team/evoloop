"""
Edge-TTS Provider (cloud-based, proxies to msedge-tts crate via Rust)
"""

import asyncio
import logging
from typing import Any

import httpx

from app.infrastructure.voice.tts.base import BaseTTSProvider, TTSOptions, TTSResult

logger = logging.getLogger(__name__)


class EdgeTTSProvider(BaseTTSProvider):
    name = "edge-tts"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    def is_available(self) -> bool:
        return True

    def list_voices(self) -> list[str]:
        return ["zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", "zh-CN-YunjianNeural",
                "zh-CN-XiaoyiNeural", "en-US-JennyNeural", "en-US-GuyNeural"]

    async def load_model(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)

    async def generate(self, options: TTSOptions) -> TTSResult:
        # This is a wrapper - actual synthesis happens in Rust via msedge-tts crate
        raise NotImplementedError("Edge-TTS should be called from Rust directly")
