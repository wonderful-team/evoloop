import pytest

lancedb = pytest.importorskip("lancedb")  # noqa: F401

from app.core.routing import retriever  # noqa: E402
from app.core.routing.index import RouteIndex  # noqa: E402
from app.core.routing.schemas import RouteCandidate  # noqa: E402


def _vec(seed: float, dim: int = 8) -> list[float]:
    return [seed + i * 0.01 for i in range(dim)]


class _FakeEmbedder:
    def __init__(self, vec: list[float]):
        self._vec = vec
        self.queries: list[str] = []

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return self._vec


@pytest.mark.asyncio
async def test_retrieve_returns_candidates(tmp_path, monkeypatch):
    idx = RouteIndex(str(tmp_path / "v"), dim=8)
    entries = [
        {"id": "skill:42", "type": "skill", "name": "播放音乐", "description": "播放歌曲", "params_schema": {}, "target": "42"},
        {"id": "local:open_app", "type": "local", "name": "open_app", "description": "打开应用", "params_schema": {"app": "str"}, "target": "open_app"},
    ]
    idx.upsert(entries, [_vec(0.2), _vec(0.9)])

    fake = _FakeEmbedder(_vec(0.2))
    monkeypatch.setattr(retriever, "_get_embedder", lambda: fake)
    monkeypatch.setattr(retriever, "get_index", lambda: idx)

    out = await retriever.retrieve("播放周杰伦的晴天", top_k=2)

    assert fake.queries == ["播放周杰伦的晴天"]
    assert len(out) == 2
    assert all(isinstance(c, RouteCandidate) for c in out)
    assert out[0].id == "skill:42"
    assert out[0].params_schema == {}


@pytest.mark.asyncio
async def test_retrieve_no_embedder_returns_empty(tmp_path, monkeypatch):
    idx = RouteIndex(str(tmp_path / "v"), dim=8)
    monkeypatch.setattr(retriever, "_get_embedder", lambda: None)
    monkeypatch.setattr(retriever, "get_index", lambda: idx)

    out = await retriever.retrieve("任意", top_k=5)
    assert out == []


@pytest.mark.asyncio
async def test_retrieve_embed_failure_degrades(tmp_path, monkeypatch):
    idx = RouteIndex(str(tmp_path / "v"), dim=8)

    class _Boom:
        async def embed_query(self, _text: str) -> list[float]:
            raise RuntimeError("lmstudio down")

    monkeypatch.setattr(retriever, "_get_embedder", lambda: _Boom())
    monkeypatch.setattr(retriever, "get_index", lambda: idx)

    out = await retriever.retrieve("任意", top_k=5)
    assert out == []


def test_dedupe_by_id_keeps_first_highest_scoring():
    rows = [
        {"id": "skill:9", "name": "a", "score": 0.3},
        {"id": "skill:9", "name": "a", "score": 0.3},
        {"id": "local:paste", "name": "b", "score": 0.1},
        {"id": "skill:9", "name": "a", "score": 0.05},
    ]

    out = retriever._dedupe_by_id(rows)

    assert [r["id"] for r in out] == ["skill:9", "local:paste"]


@pytest.mark.asyncio
async def test_retrieve_dedupes_duplicate_index_rows(tmp_path, monkeypatch):
    idx = RouteIndex(str(tmp_path / "v"), dim=8)
    emb = _FakeEmbedder(_vec(0.5))
    dupes = [
        {"id": "skill:9", "type": "skill", "name": "a", "description": "", "score": 0.3},
        {"id": "skill:9", "type": "skill", "name": "a", "description": "", "score": 0.3},
    ]
    monkeypatch.setattr(retriever, "_get_embedder", lambda: emb)
    monkeypatch.setattr(retriever, "get_index", lambda: idx)
    monkeypatch.setattr(idx, "search", lambda _v, top_k: dupes)

    out = await retriever.retrieve("任意", top_k=5)

    assert [c.id for c in out] == ["skill:9"]
