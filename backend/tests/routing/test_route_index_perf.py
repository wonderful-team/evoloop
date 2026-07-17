"""Route-index scale + recall smoke (design §14.7 performance row).

Feeds 10k synthetic entries (deterministic pseudo-vectors, no real embedding) into
a throwaway RouteIndex and asserts (a) brute-force search stays under gate and
(b) recall@1 is perfect when querying with an entry's own vector. Isolates LanceDB
throughput/recall from the embedding provider. Inserts via a single batched add
(the production `upsert` deletes per-id and is O(N) in deletes — not what we
measure here).
"""

from __future__ import annotations

import math
import random
import time

import pyarrow as pa
import pytest

from app.core.routing.index import RouteIndex

_DIM = 64
_N = 10_000
_QUERIES = 50


def _vec(seed: int) -> list[float]:
    r = random.Random(seed)
    v = [r.gauss(0.0, 1.0) for _ in range(_DIM)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


@pytest.mark.unit
@pytest.mark.slow
@pytest.mark.timeout(180)
def test_route_index_10k_search_latency_and_recall(tmp_path) -> None:
    idx = RouteIndex(db_path=str(tmp_path / "v"), dim=_DIM)

    vectors = [_vec(i) for i in range(_N)]
    data = pa.table({
        "id": [f"skill:{i}" for i in range(_N)],
        "type": ["skill"] * _N,
        "name": [f"s{i}" for i in range(_N)],
        "description": [f"entry {i}" for i in range(_N)],
        "params_schema": ["{}"] * _N,
        "execution_mode": [""] * _N,
        "target": [""] * _N,
        "vector": vectors,
    })
    t0 = time.perf_counter()
    idx._table.add(data)  # single batched insert (perf test only)
    insert_ms = (time.perf_counter() - t0) * 1e3
    assert idx.count() == _N

    lat: list[float] = []
    for q in range(_QUERIES):
        s = time.perf_counter()
        idx.search(_vec(q), top_k=20)
        lat.append((time.perf_counter() - s) * 1e3)
    lat.sort()
    p95 = lat[int(len(lat) * 0.95)]

    hits = 0
    for q in range(_QUERIES):
        rows = idx.search(_vec(q), top_k=1)
        if rows and rows[0]["id"] == f"skill:{q}":
            hits += 1
    recall = hits / _QUERIES

    assert p95 < 50.0, f"search p95={p95:.2f} ms (target <10 ms, gate <50 ms for CI)"
    assert recall >= 0.99, f"recall@1={recall:.3f}"
    assert insert_ms < 60_000, f"batched insert {insert_ms:.0f} ms too slow"
