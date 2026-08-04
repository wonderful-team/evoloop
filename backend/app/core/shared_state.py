"""
SharedState — process-wide singleton key-value store.

Acts as the Single Source of Truth (SSOT) for cross-layer state shared
between Python, Rust, and React. Every write triggers a publish event
so that subscribers can push updates to WS (Rust) and SSE (React).

Default keys:
  - project_id  (str)  — current active project
  - thread_id   (str)  — current voice session thread
  - TTS_ENGINE  (str)  — selected TTS engine
  - TTS_VOICE   (str)  — selected TTS voice
  - TTS_SPEED   (str)  — TTS playback speed
  - QWEN_TTS_API_KEY (str) — API key for Qwen TTS
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class SharedState:
    """Process-wide singleton key-value store."""

    _instance: SharedState | None = None

    def __new__(cls) -> SharedState:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._store: dict[str, str] = {
                "project_id": "0",
                "thread_id": "",
                "TTS_ENGINE": "edge-tts",
                "TTS_VOICE": "zh-CN-XiaoxiaoNeural",
                "TTS_SPEED": "1.0",
                "QWEN_TTS_API_KEY": "",
                "SEEDUPLEX_APP_ID": "",
                "SEEDUPLEX_ACCESS_KEY": "",
            }
            cls._instance._lock = asyncio.Lock()
            cls._instance._handlers: dict[str, list[callable]] = {}
        return cls._instance

    async def get(self, key: str, default: str = "") -> str:
        async with self._lock:
            return self._store.get(key, default)

    async def set(self, key: str, value: str) -> tuple[str, str]:
        old = ""
        async with self._lock:
            old = self._store.get(key, "")
            self._store[key] = value
        if old != value:
            logger.info("[shared-state] %s: %s → %s", key, old, value)
            await self._publish(key, old, value)
        return (old, value)

    async def get_all(self) -> dict[str, str]:
        async with self._lock:
            return dict(self._store)

    async def _publish(self, key: str, old_value: str, new_value: str) -> None:
        from app.core.events.publishers import publish_state_changed

        await publish_state_changed(key=key, old_value=old_value, new_value=new_value)


shared_state = SharedState()
