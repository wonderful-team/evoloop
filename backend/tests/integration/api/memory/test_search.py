"""Integration tests for /search memory routes
(app/api/routes/memory/search.py).

Covers the three endpoints:
- GET /search (memory text search)
- GET /search/vector (vector search)
- GET /search/hybrid (hybrid vector + text search)

Vector search depends on embedder + vector store; these are mocked at the
route boundary (EmbedderFactory / get_vector_store).
"""

from __future__ import annotations

from types import SimpleNamespace

from app.core.memory.models import MemoryEntry, MemoryType


def _make_entry(title: str = "MyConcept", **overrides) -> MemoryEntry:
    return MemoryEntry(
        id=f"concept_{title.lower().replace(' ', '_')}",
        type=MemoryType.CONCEPT,
        title=title,
        content="desc",
        description="desc",
        **overrides,
    )


class SyncStub:
    """Sync callable returning a preset value (used via ``asyncio.to_thread``)."""

    def __init__(self, return_value):
        self._return_value = return_value

    def __call__(self, *args, **kwargs):
        return self._return_value


class _StubEmbedder:
    def __init__(self, query_embedding=(0.1, 0.2)):
        self._query_embedding = query_embedding

    async def aembed_query(self, query):
        return self._query_embedding


class _FailEmbedder:
    async def aembed_query(self, query):
        raise RuntimeError("embedding api down")


def _patch_vector_boundaries(monkeypatch, *, results=None, embedder=None):
    """Patch EmbedderFactory / get_vector_store used by the search routes.

    Returns the fake vector store.
    """
    store = SimpleNamespace(search_code=SyncStub(results or []))
    embedder_inst = embedder if embedder is not None else _StubEmbedder()

    class _Factory:
        @staticmethod
        def get_embedder():
            return embedder_inst

    monkeypatch.setattr("app.api.routes.memory.search.EmbedderFactory", _Factory)
    monkeypatch.setattr(
        "app.api.routes.memory.search.get_vector_store",
        SyncStub(store),
    )
    return store


def _sample_hit(**overrides) -> dict:
    hit = {
        "id": "r1",
        "content": "c",
        "file_path": "f.py",
        "repository_id": "1",
        "chunk_type": "code",
        "identifier": "i",
        "start_line": 1,
        "end_line": 2,
        "language": "py",
        "score": 0.8,
    }
    hit.update(overrides)
    return hit


class TestSearchMemory:
    async def test_search_memory(self, client, fake_manager):
        async def _search(**kwargs):
            assert kwargs["types"] == [MemoryType.CONCEPT]
            assert kwargs["limit"] == 10
            return [_make_entry("Alpha"), _make_entry("Beta")]

        fake_manager.search_memories = _search
        resp = await client.get("/memory/search", params={"q": "alp", "project_id": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "Alpha"

    async def test_search_memory_empty_query(self, client, fake_manager):
        resp = await client.get("/memory/search", params={"q": ""})
        assert resp.status_code == 200
        assert resp.json() == []


class TestSearchMemoryVector:
    async def test_vector_no_embedder_returns_empty(self, client, monkeypatch):
        class _NullFactory:
            @staticmethod
            def get_embedder():
                return None

        monkeypatch.setattr("app.api.routes.memory.search.EmbedderFactory", _NullFactory)
        resp = await client.get("/memory/search/vector", params={"q": "hi", "project_id": 1})
        assert resp.status_code == 200
        assert resp.json()["results"] == []
        assert resp.json()["search_type"] == "vector"

    async def test_vector_search(self, client, monkeypatch):
        _patch_vector_boundaries(monkeypatch, results=[_sample_hit(score=0.9)])
        resp = await client.get("/memory/search/vector", params={"q": "foo", "project_id": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["results"][0]["id"] == "r1"
        assert data["results"][0]["score"] == 0.9

    async def test_vector_empty_query(self, client, monkeypatch):
        resp = await client.get("/memory/search/vector", params={"q": ""})
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    async def test_vector_search_500(self, client, monkeypatch):
        _patch_vector_boundaries(monkeypatch, embedder=_FailEmbedder())
        resp = await client.get("/memory/search/vector", params={"q": "foo", "project_id": 1})
        assert resp.status_code == 500


class TestSearchMemoryHybrid:
    async def test_hybrid_search(self, client, fake_manager, monkeypatch):
        _patch_vector_boundaries(monkeypatch, results=[_sample_hit()])

        async def _search(**_kwargs):
            return [_make_entry("Alpha")]

        fake_manager.search_memories = _search
        resp = await client.get("/memory/search/hybrid", params={"q": "foo", "project_id": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["search_type"] == "hybrid"
        assert data["vector_results_count"] == 1
        assert data["text_results_count"] == 1
        types = {item["type"] for item in data["results"]}
        assert types == {"vector", "text"}

    async def test_hybrid_empty_query(self, client, fake_manager):
        resp = await client.get("/memory/search/hybrid", params={"q": ""})
        assert resp.status_code == 200
        assert resp.json()["search_type"] == "hybrid"
        assert resp.json()["total"] == 0

    async def test_hybrid_falls_back_to_text(self, client, fake_manager, monkeypatch):
        _patch_vector_boundaries(monkeypatch, embedder=_FailEmbedder())

        async def _concepts(*_a, **_kw):
            return [{"name": "Alpha", "description": "desc"}]

        fake_manager.search_concepts_data = _concepts
        resp = await client.get("/memory/search/hybrid", params={"q": "foo", "project_id": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["search_type"] == "text_fallback"
        assert data["total"] == 1
