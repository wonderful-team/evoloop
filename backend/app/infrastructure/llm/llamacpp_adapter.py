"""Llama.cpp in-process adapter for Lightning Channel."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

logger = logging.getLogger(__name__)


class LlamaCppChatModel:
    """Wraps a llama_cpp.Llama instance for chat completion (non-embedding mode).

    Loads the GGUF model on first use and runs all inference in a thread
    to avoid blocking the asyncio event loop.
    """

    def __init__(self, model_path: str, n_ctx: int = 8192, n_threads: int = 4):
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
        return Llama(
            model_path=self._model_path,
            n_ctx=self._n_ctx,
            n_threads=self._n_threads,
            n_gpu_layers=0,
            clip_model_path="",
            verbose=False,
        )

    async def ainvoke(self, messages: list[dict], **kwargs) -> dict:
        """Non-streaming chat completion (matches AdaptiveChatOpenAI interface).

        Returns an OpenAI-compatible dict (``{"choices": [...], ...}``).
        """
        await self._ensure_loaded()
        return await asyncio.to_thread(
            lambda: self._llm.create_chat_completion(
                messages=messages,
                **kwargs,
            )
        )

    async def astream(
        self, messages: list[dict], **kwargs
    ) -> AsyncGenerator[dict, None]:
        """Streaming chat completion (matches AdaptiveChatOpenAI interface).

        Yields OpenAI-compatible chunks.
        """
        await self._ensure_loaded()
        stream = await asyncio.to_thread(
            lambda: self._llm.create_chat_completion(
                messages=messages,
                stream=True,
                **kwargs,
            )
        )
        for chunk in stream:
            yield chunk
            await asyncio.sleep(0)

    # Alias for backward compatibility
    chat = ainvoke
    stream = astream
