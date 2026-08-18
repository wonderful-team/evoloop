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

Persistence: ``project_id`` is persisted to the DB (SystemConfig key
SHARED_STATE_PROJECT_ID) so the backend restores the active project after a
restart. Frontends (desktop/mobile) read the authoritative project_id from
the backend via SYSTEM_INIT / state_snapshot instead of keeping their own
authoritative copy — the backend is the single source of truth.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

#: DB key under which the active project_id is persisted.
_PERSISTED_KEYS = ("project_id",)
_PROJECT_PERSIST_KEY = "SHARED_STATE_PROJECT_ID"


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
            # 从 DB 恢复持久化的 active project（SSOT：后端重启后仍是用户上次选择）
            persisted = cls._instance._load_persisted()
            if persisted is not None:
                cls._instance._store["project_id"] = persisted
        return cls._instance

    @staticmethod
    def _load_persisted() -> str | None:
        """从 DB 读取持久化的 project_id（无则返回 None）。"""
        try:
            from app.infrastructure.config.service import SystemConfigService

            val = SystemConfigService.get_value(_PROJECT_PERSIST_KEY)
            return val if val else None
        except Exception as e:
            logger.warning(f"[SharedState] Failed to load persisted project_id: {e}", exc_info=True)
            return None

    async def reload_persisted(self) -> None:
        """从 DB 重新加载持久化的 project_id（覆盖当前内存值）。

        应用启动时调用，确保即使首次实例化时 DB 尚未就绪（此时恢复为 0），
        也能在 DB 初始化后补齐真实的 active project。
        """
        persisted = self._load_persisted()
        if persisted is not None:
            async with self._lock:
                old = self._store.get("project_id", "")
                if old != persisted:
                    self._store["project_id"] = persisted
                    logger.info(
                        "[shared-state] project_id restored from DB: %s → %s",
                        old, persisted,
                    )
                    await self._publish("project_id", old, persisted)

    @staticmethod
    def _persist(key: str, value: str) -> None:
        """把持久化 key 写入 DB（供重启恢复）。"""
        if key not in _PERSISTED_KEYS:
            return
        try:
            from app.infrastructure.config.service import SystemConfigService

            SystemConfigService.set_value(
                _PROJECT_PERSIST_KEY,
                value,
                description="当前活跃项目 project_id（SharedState 持久化）",
            )
        except Exception as e:
            logger.warning(f"[SharedState] Failed to persist {key}={value}: {e}", exc_info=True)

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
            self._persist(key, value)
            await self._publish(key, old, value)
        return (old, value)

    async def get_all(self) -> dict[str, str]:
        async with self._lock:
            return dict(self._store)

    async def get_active_project_id(self) -> int:
        """读取当前活跃项目 project_id（SSOT：shared_state 持久化值）。

        shared_state 是项目上下文的唯一权威来源——用户切换项目时
        ``PROJECT_SWITCHED`` 事件写入此处并持久化。所有消息入口
        （web/voice/mobile/skills）应从此处取项目，而非仅依赖请求体。
        请求体 project_id 仅用于"显式覆盖"（首次建立或切换意图）。
        """
        raw = await self.get("project_id", "0")
        try:
            return int(raw)
        except (ValueError, TypeError):
            return 0

    async def set_active_project_id(self, project_id: int) -> None:
        """设置当前活跃项目并持久化（供入口在请求显式指定时同步 SSOT）。"""
        await self.set("project_id", str(project_id))

    async def _publish(self, key: str, old_value: str, new_value: str) -> None:
        from app.core.events.publishers import publish_state_changed

        await publish_state_changed(key=key, old_value=old_value, new_value=new_value)


shared_state = SharedState()
