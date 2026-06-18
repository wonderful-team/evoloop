"""
Tests for the BatchedEmbedder wrapper.
"""
import asyncio

import pytest

from app.infrastructure.embeddings.batched import BatchedEmbedder


class FakeEmbedder:
    """Deterministic embedder for unit tests."""

    def __init__(self):
        self.calls: list[list[str]] = []

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        self.calls.append(documents)
        return [[float(i)] * 4 for i in range(len(documents))]

    async def embed_query(self, query: str) -> list[float]:
        return [1.0] * 4


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()


@pytest.mark.asyncio
async def test_batched_embedder_flushes_on_timeout(fake_embedder):
    """Two concurrent callers are combined into one batch."""
    batched = BatchedEmbedder(fake_embedder, max_batch_size=64, max_wait_ms=20)

    async def caller(docs: list[str]) -> list[list[float]]:
        return await batched.embed_documents(docs)

    results = await asyncio.gather(
        caller(["a", "b"]),
        caller(["c"]),
    )

    assert len(fake_embedder.calls) == 1
    assert fake_embedder.calls[0] == ["a", "b", "c"]
    assert results[0] == [[0.0] * 4, [1.0] * 4]
    assert results[1] == [[2.0] * 4]


@pytest.mark.asyncio
async def test_batched_embedder_flushes_on_max_batch_size(fake_embedder):
    """Batch is flushed immediately when max_batch_size is reached."""
    batched = BatchedEmbedder(fake_embedder, max_batch_size=4, max_wait_ms=5000)

    task1 = asyncio.create_task(batched.embed_documents(["a", "b"]))
    task2 = asyncio.create_task(batched.embed_documents(["c", "d"]))

    results = await asyncio.gather(task1, task2)

    assert len(fake_embedder.calls) == 1
    assert fake_embedder.calls[0] == ["a", "b", "c", "d"]
    assert len(results[0]) == 2
    assert len(results[1]) == 2


@pytest.mark.asyncio
async def test_batched_embedder_empty_input_returns_empty():
    fake_embedder = FakeEmbedder()
    batched = BatchedEmbedder(fake_embedder, max_batch_size=64, max_wait_ms=10)

    result = await batched.embed_documents([])
    assert result == []
    assert fake_embedder.calls == []


@pytest.mark.asyncio
async def test_batched_embedder_forwards_query():
    fake_embedder = FakeEmbedder()
    batched = BatchedEmbedder(fake_embedder, max_batch_size=64, max_wait_ms=10)

    result = await batched.embed_query("hello")
    assert result == [1.0] * 4
    assert fake_embedder.calls == []


@pytest.mark.asyncio
async def test_batched_embedder_close_flushes_remaining():
    fake_embedder = FakeEmbedder()
    batched = BatchedEmbedder(fake_embedder, max_batch_size=64, max_wait_ms=10000)

    task = asyncio.create_task(batched.embed_documents(["x", "y"]))
    # Give the batcher time to register the request.
    await asyncio.sleep(0.01)
    await batched.close()

    result = await task
    assert len(fake_embedder.calls) == 1
    assert fake_embedder.calls[0] == ["x", "y"]
    assert result == [[0.0] * 4, [1.0] * 4]


@pytest.mark.asyncio
async def test_batched_embedder_propagates_exception():
    class FailingEmbedder:
        async def embed_documents(self, _documents: list[str]) -> list[list[float]]:
            raise RuntimeError("embedder exploded")

        async def embed_query(self, _query: str) -> list[float]:
            return []

    batched = BatchedEmbedder(FailingEmbedder(), max_batch_size=64, max_wait_ms=10)

    with pytest.raises(RuntimeError, match="embedder exploded"):
        await batched.embed_documents(["a"])


@pytest.mark.asyncio
async def test_batched_embedder_multiple_batches(fake_embedder):
    """Requests that exceed max_batch_size are split into multiple flushes."""
    batched = BatchedEmbedder(fake_embedder, max_batch_size=3, max_wait_ms=5000)

    results = await asyncio.gather(
        batched.embed_documents(["a"]),
        batched.embed_documents(["b"]),
        batched.embed_documents(["c"]),
        batched.embed_documents(["d"]),
    )

    # The first three should fit in one batch, the fourth is flushed next.
    assert len(fake_embedder.calls) == 2
    assert len(fake_embedder.calls[0]) == 3
    assert len(fake_embedder.calls[1]) == 1
    assert len(results) == 4

    await batched.close()
