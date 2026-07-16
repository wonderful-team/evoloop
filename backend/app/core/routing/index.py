"""LanceDB-backed route index for the voice channel (Layer 1 retrieval).

Decoupled from the per-project code indexes: lives on its own global path
(`LANCEDB_ROUTE_PATH`, default `~/.evoloop/vectors`) and stores a single table
named `route_index_{dim}` so that an embedding-dimension change is detected and
triggers a rebuild rather than a silent schema error.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

logger = logging.getLogger(__name__)

_DEFAULT_DIM = 768
_ANN_THRESHOLD = 10_000


class RouteIndex:
    """Single-table LanceDB store for voice routing entries."""

    def __init__(self, db_path: str, dim: int = _DEFAULT_DIM) -> None:
        self.dim = dim
        self.table_name = f"route_index_{dim}"
        self.db_path = Path(db_path).expanduser()
        self.db_path.mkdir(parents=True, exist_ok=True)
        self._client = lancedb.connect(str(self.db_path))
        self._lock = threading.Lock()
        self._table = self._open_or_create()

    # -- schema ------------------------------------------------------------

    def _schema(self) -> pa.Schema:
        return pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("type", pa.string()),
                pa.field("name", pa.string()),
                pa.field("description", pa.string()),
                pa.field("params_schema", pa.string()),  # JSON
                pa.field("execution_mode", pa.string()),
                pa.field("target", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self.dim)),
            ]
        )

    def _open_or_create(self):
        try:
            return self._client.open_table(self.table_name)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError):
            return self._client.create_table(self.table_name, schema=self._schema())

    # -- write -------------------------------------------------------------

    @staticmethod
    def _chunks(seq: list[str], n: int):
        for i in range(0, len(seq), n):
            yield seq[i : i + n]

    def upsert(
        self, entries: list[dict[str, Any]], embeddings: list[list[float]]
    ) -> int:
        """Replace entries by id (delete-then-add) with fresh embeddings.

        Deletes are batched via `id in (...)` (500 ids per statement) instead of
        one `delete` per id — the per-id loop made a 10k-entry rebuild take
        minutes; batching keeps it sub-second.
        """
        if not entries:
            return 0
        if len(entries) != len(embeddings):
            raise ValueError("entries and embeddings must have the same length")

        with self._lock:
            ids = list(dict.fromkeys(e["id"] for e in entries))
            q = chr(39)  # single quote; keep f-string free of quote conflicts
            for chunk in self._chunks(ids, 500):
                quoted = ",".join(f"'{eid.replace(q, q * 2)}'" for eid in chunk)
                try:
                    self._table.delete(f"id in ({quoted})")
                except (ValueError, OSError, RuntimeError, TypeError, KeyError):
                    pass

            data = pa.table(
                {
                    "id": [e["id"] for e in entries],
                    "type": [e.get("type", "") for e in entries],
                    "name": [e.get("name", "") for e in entries],
                    "description": [e.get("description", "") for e in entries],
                    "params_schema": [
                        json.dumps(e.get("params_schema") or {}, ensure_ascii=False)
                        for e in entries
                    ],
                    "execution_mode": [e.get("execution_mode") or "" for e in entries],
                    "target": [e.get("target", "") for e in entries],
                    "vector": embeddings,
                }
            )
            self._table.add(data)
        return len(entries)

    def delete(self, ids: list[str]) -> int:
        if not ids:
            return 0
        with self._lock:
            for eid in ids:
                safe = eid.replace("'", "''")
                try:
                    self._table.delete(f"id = '{safe}'")
                except (ValueError, OSError, RuntimeError, TypeError, KeyError):
                    pass
        return len(ids)

    def truncate(self) -> None:
        with self._lock:
            try:
                self._table.delete("true")
            except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
                logger.warning("[RouteIndex] truncate failed: %s", exc)

    # -- read --------------------------------------------------------------

    def _get_table(self):
        """Always open the latest table version (works across worker rebuilds)."""
        try:
            return self._client.open_table(self.table_name)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError):
            return self._client.create_table(self.table_name, schema=self._schema())

    def search(
        self,
        query_vector: list[float],
        top_k: int = 20,
        type_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Vector search; returns entries with a `score` (1 - distance)."""
        query = self._get_table().search(query_vector)
        if type_filter:
            query = query.where(f"type = '{type_filter}'")
        try:
            rows = query.limit(top_k).to_list()
        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
            logger.warning("[RouteIndex] search failed: %s", exc)
            return []

        out: list[dict[str, Any]] = []
        for r in rows:
            try:
                params_schema = json.loads(r.get("params_schema") or "{}")
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "[RouteIndex] bad params_schema JSON for id=%s: %s",
                    r.get("id"),
                    exc,
                )
                params_schema = {}
            out.append(
                {
                    "id": r["id"],
                    "type": r.get("type", ""),
                    "name": r.get("name", ""),
                    "description": r.get("description", ""),
                    "params_schema": params_schema,
                    "execution_mode": r.get("execution_mode") or None,
                    "target": r.get("target", ""),
                    "score": 1.0 - float(r.get("_distance", 1.0)),
                }
            )
        return out

    def count(self) -> int:
        try:
            return self._get_table().count_rows()
        except (ValueError, OSError, RuntimeError, TypeError, KeyError):
            return 0

    @staticmethod
    def _pq_subvectors(dim: int) -> int:
        """Largest PQ sub-vector count (<=96) that divides `dim`."""
        target = min(96, dim)
        for s in range(target, 0, -1):
            if dim % s == 0:
                return s
        return 1

    def ensure_ann_index(self, threshold: int = _ANN_THRESHOLD) -> bool:
        """Build an IVF_PQ ANN index once the table is large enough.

        No-op below `threshold` (brute-force is faster for small N) or when the
        embedding dimension is too small for IVF. The metric stays L2 so the
        `score = 1 - distance` computation in `search` remains valid. Dimension
        changes are handled by the per-dim table name (`route_index_{dim}`); an
        embedding-model change is covered by the full `rebuild_route_index`
        truncate+upsert, after which the caller invokes this method again.
        """
        n = self.count()
        if n < threshold or self.dim < 16:
            return False
        num_sub = self._pq_subvectors(self.dim)
        partitions = max(32, min(1024, int(math.sqrt(n))))
        try:
            self._table.create_index(
                metric="l2",
                vector_column_name="vector",
                index_type="IVF_PQ",
                num_partitions=partitions,
                num_sub_vectors=num_sub,
                replace=True,
            )
            logger.info(
                "[RouteIndex] ANN index built (IVF_PQ, rows=%d, dim=%d, partitions=%d, sub_vectors=%d)",
                n,
                self.dim,
                partitions,
                num_sub,
            )
            return True
        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
            logger.warning(
                "[RouteIndex] ANN build failed (brute-force fallback): %s", exc
            )
            return False

    def list_entries(self, limit: int = 10000) -> list[dict[str, Any]]:
        """Diagnostic dump (without vectors) for `GET /route/index`."""
        try:
            rows = self._get_table().search().limit(limit).to_list()
        except (ValueError, OSError, RuntimeError, TypeError, KeyError):
            try:
                rows = self._get_table().to_pandas().head(limit).to_dict("records")
            except (ValueError, OSError, RuntimeError, TypeError, KeyError):
                return []
        return [
            {
                "id": r.get("id"),
                "type": r.get("type"),
                "name": r.get("name"),
                "description": r.get("description"),
            }
            for r in rows
        ]
