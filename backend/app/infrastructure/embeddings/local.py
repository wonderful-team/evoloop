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

    # Hard cap on the number of texts passed to a single encode() call. Larger
    # batches run faster per-text but a single huge call monopolizes the CPU for
    # minutes and makes the whole machine unresponsive. 32 is a sweet spot for
    # the BCE model on a typical laptop CPU.
    _MAX_ENCODE_BATCH = 32

    def __init__(
        self, model_name: str = "maidalun1020/bce-embedding-base_v1", device: str = "cpu"
    ):
        self.model_name = model_name
        self.device = device
        self._model = None

        # Determine if we need asymmetric prefixes
        # BCE uses Query:/Passage:, Nomic uses search_query:/search_document:
        self._needs_prefix = "bce" in model_name.lower() or "nomic" in model_name.lower()
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
                # Another thread is loading; wait asynchronously and loop back.
                while not loading_event.is_set():
                    await asyncio.sleep(0.05)

    _FALLBACK_MODELS = [
        "maidalun1020/bce-embedding-base_v1",
        "sentence-transformers/all-MiniLM-L6-v2",
        "nomic-ai/nomic-embed-text-v1.5",
    ]

    def _load_model_sync(self):
        """Construct the SentenceTransformer model synchronously."""
        os.environ.setdefault("OMP_NUM_THREADS", "2")
        os.environ.setdefault("MKL_NUM_THREADS", "2")

        import torch
        torch.set_num_threads(2)
        import huggingface_hub.constants as _st_cache
        from sentence_transformers import SentenceTransformer

        candidates = [self.model_name]
        if self.model_name != self._FALLBACK_MODELS[0]:
            candidates.extend(self._FALLBACK_MODELS)
        else:
            candidates.extend(self._FALLBACK_MODELS[1:])

        last_error = None
        for model_name in candidates:
            logger.info(f"[LocalEmbedder] Trying model '{model_name}' on {self.device}...")
            try:
                loaded = SentenceTransformer(
                    model_name,
                    device=self.device,
                    trust_remote_code=True,
                    cache_folder=_st_cache.default_cache_path,
                    local_files_only=True,
                )
                if model_name != self.model_name:
                    logger.warning(
                        f"[LocalEmbedder] Configured model '{self.model_name}' unavailable; "
                        f"using '{model_name}' instead."
                    )
                else:
                    logger.info("[LocalEmbedder] Model loaded.")
                return loaded
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                last_error = e
                logger.warning(f"[LocalEmbedder] Failed to load '{model_name}': {e}")
                continue

        raise RuntimeError(
            f"No embedding model could be loaded. Tried: {candidates}. "
            f"Last error: {last_error}"
        )

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        if not documents:
            return []

        # Prepend prefix for asymmetric models
        processed_docs = documents
        if self._is_nomic:
            processed_docs = [
                f"search_document: {doc}" if not doc.startswith("search_") else doc
                for doc in documents
            ]
        elif "bce" in self.model_name.lower():
            processed_docs = [
                f"Passage: {doc}" if not doc.startswith("Passage:") else doc
                for doc in documents
            ]

        model = await self._get_model()
        logger.debug(f"[LocalEmbedder] Embedding {len(documents)} documents...")

        # Serialize encode() across worker threads. The lock is held only for
        # the duration of the (CPU-bound) encode call. encode() is called
        # synchronously to avoid asyncio.to_thread / PyTorch thread-pool
        # deadlocks observed in Huey worker threads on macOS.
        #
        # We also cap the batch size and disable the progress bar: a single
        # huge encode() call monopolizes the CPU for minutes and makes the
        # whole machine unresponsive.
        all_embeddings: list[list[float]] = []
        with LocalEmbedder._encode_lock:
            for i in range(0, len(processed_docs), LocalEmbedder._MAX_ENCODE_BATCH):
                chunk = processed_docs[i : i + LocalEmbedder._MAX_ENCODE_BATCH]
                embeddings = model.encode(
                    chunk,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )
                all_embeddings.extend(embeddings.tolist())
        return all_embeddings

    async def embed_query(self, query: str) -> list[float]:
        if not query:
            return [0.0] * 768

        # Prepend prefix for asymmetric models
        processed_query = query
        if self._is_nomic and not query.startswith("search_"):
            processed_query = f"search_query: {query}"
        elif "bce" in self.model_name.lower() and not query.startswith("Query:"):
            processed_query = f"Query: {query}"

        model = await self._get_model()
        logger.debug(f"[LocalEmbedder] Embedding query: {query[:50]}...")

        # Serialize encode() across worker threads.
        # Use the same small batch cap so queries do not block large batches.
        with LocalEmbedder._encode_lock:
            embedding = model.encode(
                processed_query,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        return embedding.tolist()

    # Compatibility aliases
    aembed_documents = embed_documents
    aembed_query = embed_query
