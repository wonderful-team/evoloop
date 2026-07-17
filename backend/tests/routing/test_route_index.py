import pytest

lancedb = pytest.importorskip("lancedb")  # noqa: F401

from app.core.routing.index import RouteIndex  # noqa: E402


def _vec(seed: float, dim: int = 8) -> list[float]:
    return [seed + i * 0.01 for i in range(dim)]


def test_upsert_search_delete(tmp_path):
    idx = RouteIndex(str(tmp_path / "v"), dim=8)
    entries = [
        {"id": "local:open_app", "type": "local", "name": "open_app", "description": "打开应用", "params_schema": {"app": "str"}, "target": "open_app"},
        {"id": "skill:42", "type": "skill", "name": "播放音乐", "description": "播放歌曲", "params_schema": {}, "target": "42"},
        {"id": "agent:default", "type": "agent", "name": "Agent 兜底", "description": "复杂任务", "params_schema": {}, "target": "default"},
    ]
    vecs = [_vec(0.1), _vec(0.2), _vec(0.3)]
    assert idx.upsert(entries, vecs) == 3
    assert idx.count() == 3

    res = idx.search(_vec(0.2), top_k=2)
    assert len(res) == 2
    assert res[0]["id"] == "skill:42"
    assert 0.0 <= res[0]["score"] <= 1.0
    assert res[0]["params_schema"] == {}

    assert idx.delete(["skill:42"]) == 1
    assert idx.count() == 2

    dump = idx.list_entries()
    assert len(dump) == 2
    assert all("vector" not in r for r in dump)


def test_dimensioned_table_name(tmp_path):
    idx = RouteIndex(str(tmp_path / "v"), dim=16)
    assert idx.table_name == "route_index_16"


def test_upsert_replaces_same_id_without_bloat(tmp_path):
    import time

    idx = RouteIndex(str(tmp_path / "v"), dim=8)
    entries = [
        {"id": f"skill:{i}", "type": "skill", "name": f"s{i}", "description": f"e{i}"}
        for i in range(1000)
    ]
    vecs = [_vec(float(i) * 0.001) for i in range(1000)]

    idx.upsert(entries, vecs)
    assert idx.count() == 1000

    # re-upsert the SAME ids with fresh vectors: must replace, not append
    t0 = time.perf_counter()
    idx.upsert(entries, [[0.5] * 8 for _ in range(1000)])
    elapsed = time.perf_counter() - t0

    assert idx.count() == 1000  # no row bloat from re-upsert
    assert elapsed < 2.0, f"batched-delete upsert too slow: {elapsed:.2f}s"
