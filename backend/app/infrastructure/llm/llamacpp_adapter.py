"""Llama.cpp in-process adapter for Lightning Channel."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)


class LlamaCppChatModel:
    """Wraps a llama_cpp.Llama instance for chat completion (non-embedding mode).

    Loads the GGUF model on first use and runs all inference in a thread
    to avoid blocking the asyncio event loop.

    On Apple Silicon, uses Metal GPU acceleration via ``n_gpu_layers=-1``.
    """

    model: str = "llama.cpp"

    def __init__(self, model_path: str, n_ctx: int = 8192, n_threads: int = 8):
        self._model_path = os.path.expanduser(model_path)
        self._n_ctx = n_ctx
        self._n_threads = n_threads
        self._llm: Any = None
        self._lock = asyncio.Lock()

    async def _ensure_loaded(self):
        if self._llm is not None:
            return
        async with self._lock:
            if self._llm is not None:
                return
            logger.info(
                "[LlamaCpp] Loading chat model: %s (ctx=%s, threads=%s)",
                self._model_path, self._n_ctx, self._n_threads,
            )
            self._llm = await asyncio.to_thread(
                lambda: self._import_and_build()
            )
            logger.info("[LlamaCpp] Chat model loaded.")

    def _import_and_build(self):
        from llama_cpp import Llama
        import platform
        n_gpu = -1 if platform.system() == "Darwin" else 0
        logger.info(
            "[LlamaCpp] Using n_gpu_layers=%d on %s",
            n_gpu, platform.system(),
        )
        return Llama(
            model_path=self._model_path,
            n_ctx=self._n_ctx,
            n_threads=self._n_threads,
            n_gpu_layers=n_gpu,
            clip_model_path="",
            verbose=False,
        )

    async def ainvoke(self, messages: list[dict], **kwargs) -> dict:
        """Non-streaming chat completion (matches AdaptiveChatOpenAI interface).

        Returns an OpenAI-compatible dict (``{"choices": [...], ...}``).
        """
        await self._ensure_loaded()
        kwargs.pop("config", None)
        return await asyncio.to_thread(
            lambda: self._llm.create_chat_completion(
                messages=messages,
                **kwargs,
            )
        )

    async def astream(
        self, messages: list[dict], **kwargs
    ) -> AsyncGenerator[Any, None]:
        """Streaming chat completion (matches AdaptiveChatOpenAI interface).

        Yields AIMessageChunk objects compatible with the inference engine.
        """
        from app.core.engine.message.native_classes import AIMessageChunk

        await self._ensure_loaded()
        kwargs.pop("config", None)
        stream = await asyncio.to_thread(
            lambda: self._llm.create_chat_completion(
                messages=messages,
                stream=True,
                **kwargs,
            )
        )
        for chunk in stream:
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content", "")
            if content:
                yield AIMessageChunk(content=content)
            elif delta.get("role") == "assistant":
                # First chunk with role only — yield empty to signal start
                yield AIMessageChunk(content="")
            await asyncio.sleep(0)

    # Alias for backward compatibility
    chat = ainvoke
    stream = astream

    def bind_tools(self, tools: list[Any]) -> "LlamaCppChatModel":
        """Compatibility with InferenceEngine.bind_tools."""
        return self
