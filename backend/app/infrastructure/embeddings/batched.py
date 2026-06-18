"""
BatchedEmbedder: Collects embedding requests from multiple concurrent file
indexers and flushes them as a single model.encode() batch.

In embedded mode the local SentenceTransformer model is CPU-bound and the
encode() call is serialized across worker threads. Calling encode() once per
file wastes throughput because small batches have high fixed overhead. This
wrapper buffers requests from concurrent coroutines, waits a short timeout for
more requests to arrive, and then calls the underlying embedder with the
combined batch. The returned embeddings are routed back to the original callers.

Thread-safety: BatchedEmbedder is designed to run inside a single event loop
(e.g. one Huey worker thread). It uses only asyncio primitives and is not shared
across OS threads.
"""
import asyncio
import logging
from typing import Any

from app.infrastructure.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)


class _PendingRequest:
    """Internal request object submitted by a caller."""

    def __init__(self, texts: list[str]):
        self.texts = texts
        self.future: asyncio.Future[list[list[float]]] = asyncio.get_running_loop().create_future()


class BatchedEmbedder(BaseEmbedder):
    """
    Wrapper around a BaseEmbedder that batches concurrent embed_documents()
    calls.

    Args:
        embedder: The underlying embedder to invoke with batched inputs.
        max_batch_size: Maximum number of texts in a single batch. When this
            many texts have accumulated, flush immediately.
        max_wait_ms: Maximum time to wait for additional requests before
            flushing a partial batch.
    """

    def __init__(
        self,
        embedder: BaseEmbedder,
        max_batch_size: int = 64,
        max_wait_ms: float = 50.0,
    ):
        self._embedder = embedder
        self._max_batch_size = max(max_batch_size, 1)
        self._max_wait_s = max(max_wait_ms / 1000.0, 0.001)
        self._lock = asyncio.Lock()
        self._pending: list[_PendingRequest] = []
        self._flush_task: asyncio.Task[Any] | None = None

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        if not documents:
            return []

        request = _PendingRequest(documents)
        async with self._lock:
            self._pending.append(request)
            total_texts = sum(len(r.texts) for r in self._pending)
            if total_texts >= self._max_batch_size and self._flush_task is None:
                # Batch is full; flush immediately without waiting for timeout.
                self._flush_task = asyncio.create_task(self._flush())
            elif self._flush_task is None:
                self._flush_task = asyncio.create_task(self._scheduled_flush())
        return await request.future

    async def embed_query(self, query: str) -> list[float]:
        # Queries are usually one-off and latency-sensitive; do not batch them.
        return await self._embedder.embed_query(query)

    async def _scheduled_flush(self) -> None:
        """Wait briefly, then flush whatever is in the buffer."""
        try:
            await asyncio.sleep(self._max_wait_s)
        except asyncio.CancelledError:
            # A new request pushed us over the batch limit; re-schedule flush.
            return
        await self._flush()

    async def _flush(self) -> None:
        """Combine pending requests into one or more batches and call the embedder."""
        async with self._lock:
            self._flush_task = None
            if not self._pending:
                return

            # Consume up to max_batch_size texts in this flush. Leave any
            # overflow in pending for the next scheduled flush.
            requests: list[_PendingRequest] = []
            remaining: list[_PendingRequest] = []
            total_texts = 0
            for req in self._pending:
                if total_texts + len(req.texts) <= self._max_batch_size or not requests:
                    requests.append(req)
                    total_texts += len(req.texts)
                else:
                    remaining.append(req)
            self._pending = remaining
            if remaining and self._flush_task is None:
                self._flush_task = asyncio.create_task(self._scheduled_flush())

        all_texts: list[str] = []
        offsets: list[int] = []
        for req in requests:
            offsets.append(len(all_texts))
            all_texts.extend(req.texts)

        if not all_texts:
            for req in requests:
                if not req.future.done():
                    req.future.set_result([])
            return

        logger.debug(
            f"[BatchedEmbedder] Flushing {len(requests)} requests, "
            f"{len(all_texts)} total texts"
        )
        try:
            embeddings = await self._embedder.embed_documents(all_texts)
        except Exception as exc:
            logger.exception("[BatchedEmbedder] Underlying embedder failed")
            for req in requests:
                if not req.future.done():
                    req.future.set_exception(exc)
            return

        if len(embeddings) != len(all_texts):
            err = RuntimeError(
                f"Embedder returned {len(embeddings)} embeddings for "
                f"{len(all_texts)} texts"
            )
            for req in requests:
                if not req.future.done():
                    req.future.set_exception(err)
            return

        for req, offset in zip(requests, offsets, strict=False):
            if req.future.done():
                continue
            end = offset + len(req.texts)
            req.future.set_result(embeddings[offset:end])

    async def close(self) -> None:
        """Flush any remaining requests and clean up."""
        async with self._lock:
            if self._flush_task is not None:
                self._flush_task.cancel()
                self._flush_task = None
        await self._flush()
        pending = []
        async with self._lock:
            pending = self._pending
            self._pending = []
        for req in pending:
            if not req.future.done():
                req.future.cancel()

    # LangChain-compatible alias
    aembed_documents = embed_documents
    aembed_query = embed_query
