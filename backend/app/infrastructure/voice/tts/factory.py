"""
TTS Provider Factory

Lazy-loads TTS providers by name, caches instances.
"""

import asyncio
import logging
from typing import Any

from app.infrastructure.voice.tts.base import BaseTTSProvider

logger = logging.getLogger(__name__)

_providers: dict[str, BaseTTSProvider] = {}
_provider_locks: dict[str, asyncio.Lock] = {}


def _lock_for(name: str) -> asyncio.Lock:
    if name not in _provider_locks:
        _provider_locks[name] = asyncio.Lock()
    return _provider_locks[name]


async def get_tts_provider(engine: str) -> BaseTTSProvider:
    if engine in _providers:
        return _providers[engine]

    async with _lock_for(engine):
        if engine in _providers:
            return _providers[engine]

        provider = _create_provider(engine)
        if provider is None:
            raise ValueError(f"Unsupported TTS engine: {engine}")
        await provider.load_model()
        _providers[engine] = provider
        logger.info("[TTSFactory] %s provider loaded", engine)
        return provider


def _create_provider(engine: str) -> BaseTTSProvider | None:
    if engine == "cosyvoice":
        from app.infrastructure.voice.tts.cosyvoice_provider import CosyVoiceTTSProvider
        return CosyVoiceTTSProvider()
    if engine in ("edge-tts", "edge"):
        from app.infrastructure.voice.tts.edge_provider import EdgeTTSProvider
        return EdgeTTSProvider()
    if engine in ("qwen-tts", "qwen"):
        from app.infrastructure.voice.tts.qwen_provider import QwenTTSProvider
        return QwenTTSProvider()
    return None
