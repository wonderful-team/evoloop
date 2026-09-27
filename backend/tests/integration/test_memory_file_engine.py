"""Verification of memory file_engine refactors.

- _db_delete_by_run_id/_source_message_id/_source_thread_id → _db_delete_by_column
- _row_to_dict extraction (21-field serialization)
- dead-code removal: _db_list_all, _db_get_by_id, _DBIndexProxy, index_db
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.memory import file_engine as file_engine_module
from app.core.memory.file_engine import _FileEngine
from app.models.memory import MemoryIndex


def _make_index(memory_id: str = "mem-1", thread_id: str = "t-1") -> MemoryIndex:
    now = datetime.now(timezone.utc)
    return MemoryIndex(
        id=memory_id,
        type="concept",
        tier="hot",
        privacy="private",
        title="Title",
        description="Desc",
        path="/tmp/x.md",
        project_id=1,
        member_id=0,
        source="s",
        source_thread_id=thread_id,
        source_run_id="run-1",
        created_at=now,
        updated_at=now,
    )


class TestRowToDict:
    def test_serializes_all_fields(self) -> None:
        row = _make_index()
        d = _FileEngine._row_to_dict(row)
        assert d["id"] == "mem-1"
        assert d["run_id"] == "run-1"
        assert d["source_thread_id"] == "t-1"
        assert d["title"] == "Title"
        assert d["created_at"].endswith("+00:00")
        assert "updated_at" in d

    def test_nullable_datetimes_become_none(self) -> None:
        row = MemoryIndex(
            id="m",
            type="t",
            tier="h",
            privacy="p",
            title="T",
            path="/p",
        )
        d = _FileEngine._row_to_dict(row)
        assert d["created_at"] is None
        assert d["updated_at"] is None


class TestDeadCodeRemoved:
    def test_removed_methods_do_not_exist(self) -> None:
        assert not hasattr(_FileEngine, "_db_list_all")
        assert not hasattr(_FileEngine, "_db_get_by_id")
        assert not hasattr(_FileEngine, "_db_delete_by_run_id")
        assert not hasattr(_FileEngine, "_db_delete_by_source_message_id")

    def test_proxy_and_index_db_removed(self) -> None:
        assert not hasattr(file_engine_module, "_DBIndexProxy")
        engine = _FileEngine(base_dir="/tmp/nonexistent-evo-test")
        assert not hasattr(engine, "index_db")


class TestDbDeleteByColumn:
    async def test_deletes_by_thread_id_and_returns_count(
        self, test_session_scope, monkeypatch
    ) -> None:
        monkeypatch.setattr(file_engine_module, "session_scope", test_session_scope)
        engine = _FileEngine(base_dir="/tmp/nonexistent-evo-test")

        async with test_session_scope() as session:
            session.add(_make_index("a", thread_id="t-1"))
            session.add(_make_index("b", thread_id="t-1"))
            session.add(_make_index("c", thread_id="t-2"))

        deleted = await engine._db_delete_by_source_thread_id("t-1")
        assert deleted == 2

        async with test_session_scope() as session:
            from sqlalchemy import select

            remaining = (await session.execute(select(MemoryIndex))).scalars().all()
        assert len(remaining) == 1
        assert remaining[0].id == "c"
