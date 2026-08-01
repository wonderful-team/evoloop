"""Lightning Channel — lightweight local LLM for routing.

Manages the lifecycle of a lightweight local LLM instance (for routing
decisions, classification, etc.) based on the LIGHTNING_MODE config.

Embedding is handled independently by EmbedderFactory (see
``app/infrastructure/embeddings/factory.py``) and is NOT managed here.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any

from app.infrastructure.config import SystemConfigService
from app.infrastructure.llm.adaptive import AdaptiveChatOpenAI
from app.infrastructure.llm.llamacpp_adapter import LlamaCppChatModel

logger = logging.getLogger(__name__)

_LIGHTNING_DEFAULTS = {
    "lm-studio": {
        "base_url": "http://localhost:1234/v1",
        "api_key": "lm-studio",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "api_key": "",
    },
}


class LightningMode(str, Enum):
    NONE = "none"
    LLAMA_CPP = "llama.cpp"
    LM_STUDIO = "lm-studio"
    OLLAMA = "ollama"


def _cfg(key: str, default: str | None = None) -> str | None:
    try:
        return SystemConfigService.get_value(key, default)
    except Exception:
        return default


class LightningService:
    """Singleton that creates and caches a Lightning Channel LLM instance.

    The LLM is used exclusively for lightweight tasks:
    - Route decisions in :mod:`app.core.routing.router`
    - Intent decomposition in :mod:`app.core.routing.decompose`

    Embedding is NOT managed here — see :class:`EmbedderFactory`.
    """

    def __init__(self):
        self._llm: Any = None
        self._config_snapshot: dict[str, str | None] = {}

    def _snapshot(self) -> dict[str, str | None]:
        return {
            "mode": _cfg("LIGHTNING_MODE", "none"),
            "llm_model": _cfg("LIGHTNING_LLM_MODEL", ""),
            "ctx": _cfg("LIGHTNING_CTX", "8192"),
            "base_url": _cfg("LIGHTNING_BASE_URL", ""),
            "api_key": _cfg("LIGHTNING_API_KEY", ""),
        }

    def _dirty(self) -> bool:
        return self._snapshot() != self._config_snapshot

    # ---- public API --------------------------------------------------------

    async def get_llm(self) -> Any | None:
        """Return the Lightning Channel LLM, or None if mode is ``none``."""
        if self._dirty():
            self.flush()

        if self._llm is not None:
            return self._llm

        snap = self._snapshot()
        mode = snap["mode"]
        if mode == LightningMode.NONE.value:
            return None

        self._llm = await self._build_llm(snap)
        self._config_snapshot = snap
        await self._warmup_if_llamacpp()
        return self._llm

    async def _warmup_if_llamacpp(self):
        """Preload the llama.cpp model and warm up Metal JIT."""
        if not isinstance(self._llm, LlamaCppChatModel):
            return
        try:
            await self._llm._ensure_loaded()
            # Tiny inference to warm Metal shader cache
            await asyncio.to_thread(
                lambda: self._llm._llm.create_completion("Hi", max_tokens=1, temperature=0)
            )
            logger.info("[Lightning] llama.cpp model warmed up (Metal JIT compiled)")
        except Exception as e:
            logger.warning("[Lightning] llama.cpp warmup failed: %s", e)

    def flush(self):
        """Drop the cached LLM instance so it is re-created on next access."""
        self._llm = None
        self._config_snapshot = {}
        logger.debug("[Lightning] Cache flushed")

    # ---- factory internals -------------------------------------------------

    async def _build_llm(self, snap: dict[str, str | None]) -> Any:
        mode = snap["mode"]
        logger.info("[Lightning] Building LLM for mode=%s", mode)

        if mode == LightningMode.LLAMA_CPP.value:
            model_path = snap["llm_model"] or ""
            if not model_path:
                raise ValueError(
                    "LIGHTNING_LLM_MODEL must be set when LIGHTNING_MODE=llama.cpp"
                )
            ctx = int(snap["ctx"] or "8192")
            return LlamaCppChatModel(model_path=model_path, n_ctx=ctx)

        base_url = snap["base_url"] or ""
        api_key = snap["api_key"] or ""
        if not base_url:
            defaults = _LIGHTNING_DEFAULTS.get(mode, {})
            base_url = defaults.get("base_url", "http://localhost:1234/v1")
            api_key = defaults.get("api_key", "lm-studio")

        model = snap["llm_model"] or ""
        return AdaptiveChatOpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            model=model,
            temperature=0.0,
            streaming=False,
            max_tokens=256,
        )


# Global singleton
_lightning_service: LightningService | None = None


def get_lightning_service() -> LightningService:
    global _lightning_service
    if _lightning_service is None:
        _lightning_service = LightningService()
    return _lightning_service


def reset_lightning_service():
    """Test helper — clear the singleton and all cached instances."""
    global _lightning_service
    if _lightning_service is not None:
        _lightning_service.flush()
    _lightning_service = None
