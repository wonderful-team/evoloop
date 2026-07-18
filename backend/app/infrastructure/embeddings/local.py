import asyncio
import logging
import os
import threading
from typing import Any

from app.infrastructure.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)


class LocalEmbedder(BaseEmbedder):
    """Local embedding model via llama-cpp-python (GGUF).

    Thread-safety:
        - The Llama model instance is shared across Huey worker threads, but
          its encode() method is NOT safe under concurrent calls from multiple
          independent event loops. We serialize create_embedding() calls with
          a per-instance threading.Lock.
        - Model loading uses a process-wide single-flight cache so that only
          one thread actually constructs the model, even when many workers race
          to initialize it.
    """

    _shared_model_cache: dict[str, Any] = {}
    _loading_flags: dict[str, threading.Event] = {}
    _model_load_lock = threading.Lock()

    _encode_lock = threading.Lock()
    _MAX_ENCODE_BATCH = 32

    def __init__(self, model_path: str):
        self.model_path = os.path.expanduser(model_path)
        self._model = None

        # BGE prefix logic
        name_lower = self.model_path.lower()
        self._is_bge = "bge" in name_lower
        self._use_prefix = self._is_bge

    _FALLBACK_MODELS: list[str] = []

    async def _get_model(self):
        cache_key = self.model_path

        while True:
            if self._model is not None:
                return self._model

            cached = LocalEmbedder._shared_model_cache.get(cache_key)
            if cached is not None:
                self._model = cached
                return self._model

            loading_event: threading.Event | None = None
            loading = False
            with LocalEmbedder._model_load_lock:
                cached = LocalEmbedder._shared_model_cache.get(cache_key)
                if cached is not None:
                    self._model = cached
                    return self._model

                if cache_key not in LocalEmbedder._loading_flags:
                    LocalEmbedder._loading_flags[cache_key] = threading.Event()
                    loading_event = LocalEmbedder._loading_flags[cache_key]
                    loading = True
                else:
                    loading_event = LocalEmbedder._loading_flags[cache_key]

            if loading:
                try:
                    loaded = await asyncio.to_thread(self._load_model_sync)
                    with LocalEmbedder._model_load_lock:
                        LocalEmbedder._shared_model_cache[cache_key] = loaded
                        self._model = loaded
                    return self._model
                finally:
                    loading_event.set()
                    with LocalEmbedder._model_load_lock:
                        LocalEmbedder._loading_flags.pop(cache_key, None)
            else:
                while not loading_event.is_set():
                    await asyncio.sleep(0.05)

    def _load_model_sync(self):
        from llama_cpp import Llama

        logger.info("[LocalEmbedder] Loading embedding model: %s", self.model_path)
        return Llama(
            model_path=self.model_path,
            embedding=True,
            n_ctx=512,
            n_threads=2,
            n_gpu_layers=0,
            verbose=False,
        )

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        if not documents:
            return []

        processed = []
        for doc in documents:
            if self._is_bge and not doc.startswith("为这个句子生成表示"):
                processed.append(f"为这个句子生成表示以用于检索相关文章：{doc}")
            else:
                processed.append(doc)

        model = await self._get_model()
        logger.debug("[LocalEmbedder] Embedding %d documents...", len(documents))

        all_embeddings: list[list[float]] = []
        with LocalEmbedder._encode_lock:
            for i in range(0, len(processed), LocalEmbedder._MAX_ENCODE_BATCH):
                chunk = processed[i : i + LocalEmbedder._MAX_ENCODE_BATCH]
                result = model.create_embedding(chunk)
                for item in result["data"]:
                    all_embeddings.append(item["embedding"])
        return all_embeddings

    async def embed_query(self, query: str) -> list[float]:
        if not query:
            return [0.0] * 768

        processed = query
        if self._is_bge and not query.startswith("为这个句子生成表示"):
            processed = f"为这个句子生成表示以用于检索相关文章：{query}"

        model = await self._get_model()
        logger.debug("[LocalEmbedder] Embedding query: %s...", query[:50])

        with LocalEmbedder._encode_lock:
            result = model.create_embedding(processed)
        return result["data"][0]["embedding"]

    aembed_documents = embed_documents
    aembed_query = embed_query
