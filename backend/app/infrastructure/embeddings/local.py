import asyncio
import logging
import os
import threading
from typing import Any

from app.infrastructure.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)


class LocalEmbedder(BaseEmbedder):
    """
    Local implementation of BaseEmbedder using sentence-transformers.
    Ideal for EMBEDDED_MODE where no external API is available.

    Default: nomic-ai/nomic-embed-text-v1.5 (768 dimensions)
    Note: Nomic models require search_query: and search_document: prefixes.

    Thread-safety:
        - The SentenceTransformer model instance is shared across Huey worker
          threads, but its encode() method is NOT safe under concurrent calls
          from multiple independent event loops. We serialize encode() calls
          with a per-instance threading.Lock so that only one thread uses the
          model at a time.
        - Model loading uses a process-wide single-flight cache so that only
          one coroutine (and one OS thread) actually constructs the model,
          even when many worker threads race to initialize it. Other waiters
          await asynchronously without blocking their event loops.
    """

    # Process-wide cache so that the model is loaded into memory exactly once.
    _shared_model_cache: dict[str, Any] = {}
    # Per-model-key event used to let waiters sleep until the loader finishes.
    _loading_flags: dict[str, threading.Event] = {}
    # Protects the cache and the loading_flags dict.
    _model_load_lock = threading.Lock()

    # Process-wide encode lock. The SentenceTransformer model instance is shared
    # across Huey worker threads, but encode() is NOT safe under concurrent calls
    # from multiple independent event loops. A class-level lock serializes all
    # encode() calls in the process without blocking event loops.
    _encode_lock = threading.Lock()

    def __init__(
        self, model_name: str = "nomic-ai/nomic-embed-text-v1.5", device: str = "cpu"
    ):
        self.model_name = model_name
        self.device = device
        self._model = None

        # Determine if we need Nomic-style prefixes
        self._is_nomic = "nomic" in model_name.lower()

    async def _get_model(self):
        """Return the loaded model, initializing it once across the process."""
        cache_key = f"{self.model_name}:{self.device}"

        while True:
            # Fast path: already cached on this instance.
            if self._model is not None:
                return self._model

            # Fast path: another instance already loaded the same model.
            cached = LocalEmbedder._shared_model_cache.get(cache_key)
            if cached is not None:
                self._model = cached
                return self._model

            # Single-flight: decide who loads and who waits.
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
                # This coroutine/thread is responsible for loading.
                try:
                    loaded = await self._load_model()
                    with LocalEmbedder._model_load_lock:
                        LocalEmbedder._shared_model_cache[cache_key] = loaded
                        self._model = loaded
                    return self._model
                finally:
                    loading_event.set()
                    with LocalEmbedder._model_load_lock:
                        LocalEmbedder._loading_flags.pop(cache_key, None)
            else:
                # Another thread is loading; wait asynchronously and loop back.
                while not loading_event.is_set():
                    await asyncio.sleep(0.05)

    async def _load_model(self):
        """Construct the SentenceTransformer model (called once per process)."""
        # Force offline mode to guarantee zero network requests to HuggingFace.
        # Must be set BEFORE importing sentence_transformers/huggingface_hub
        # so the library picks it up during module initialization.
        os.environ["HF_HUB_OFFLINE"] = "1"

        from sentence_transformers import SentenceTransformer

        logger.info(
            f"[LocalEmbedder] Loading model '{self.model_name}' on {self.device}..."
        )
        loaded = await asyncio.to_thread(
            SentenceTransformer,
            self.model_name,
            device=self.device,
            trust_remote_code=True,
            local_files_only=True,
        )
        logger.info("[LocalEmbedder] Model loaded from local cache.")
        return loaded

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        if not documents:
            return []

        # Prepend prefix if using Nomic
        processed_docs = documents
        if self._is_nomic:
            processed_docs = [
                f"search_document: {doc}" if not doc.startswith("search_") else doc
                for doc in documents
            ]

        model = await self._get_model()
        logger.debug(f"[LocalEmbedder] Embedding {len(documents)} documents...")

        # Serialize encode() across worker threads. The lock is held only for
        # the duration of the (CPU-bound) encode call; loading happens above.
        with LocalEmbedder._encode_lock:
            embeddings = await asyncio.to_thread(
                lambda: model.encode(processed_docs, convert_to_numpy=True)
            )
        return embeddings.tolist()

    async def embed_query(self, query: str) -> list[float]:
        if not query:
            return [0.0] * 768

        # Prepend prefix if using Nomic
        processed_query = query
        if self._is_nomic and not query.startswith("search_"):
            processed_query = f"search_query: {query}"

        model = await self._get_model()
        logger.debug(f"[LocalEmbedder] Embedding query: {query[:50]}...")

        # Serialize encode() across worker threads.
        with LocalEmbedder._encode_lock:
            embedding = await asyncio.to_thread(
                lambda: model.encode(processed_query, convert_to_numpy=True)
            )
        return embedding.tolist()

    # LangChain-compatible aliases
    aembed_documents = embed_documents
    aembed_query = embed_query
