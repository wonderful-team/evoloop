"""Coverage for the startup repair functions in skills/lifecycle.

These are synchronous DB helpers; we bind a sync engine to the shared test
SQLite file and monkeypatch the database module's sync entry points.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.learning.skills import lifecycle
from app.infrastructure.database.sql import database as dbmod
from app.models.learning import LearnedSkill, TraceEvent


def _skill(name: str, **kw) -> LearnedSkill:
    defaults = {
        "name": name,
        "description": f"desc {name}",
        "trigger_patterns": [name],
        "parameters": [],
        "status": "verified",
        "is_active": True,
    }
    defaults.update(kw)
    return LearnedSkill(**defaults)


def _trace_event(step: int, snapshot) -> TraceEvent:
    return TraceEvent(
        thread_id="t1",
        step_number=step,
        node_name="node",
        event_type="user_interaction",
        payload={},
        state_snapshot=snapshot,
    )


@pytest.fixture(autouse=True)
def _clean_db(test_session_scope):
    yield

    async def _clean():
        async with test_session_scope() as db:
            from sqlalchemy import delete

            await db.execute(delete(TraceEvent))
            await db.execute(delete(LearnedSkill))

    import asyncio

    asyncio.run(_clean())


@pytest.fixture
def sync_db_engine(test_db_path):
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{test_db_path}")
    yield engine
    engine.dispose()


@pytest.fixture
def patch_sync_db(sync_db_engine, monkeypatch):
    from contextlib import contextmanager

    from sqlalchemy.orm import Session

    @contextmanager
    def _sync_scope():
        with Session(sync_db_engine) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    monkeypatch.setattr(dbmod, "sync_session_scope", _sync_scope)
    monkeypatch.setattr(
        dbmod, "db_resource_manager", SimpleNamespace(sync_engine=sync_db_engine)
    )
    return sync_db_engine


class TestMigrateLegacyStatusRows:
    async def test_migrates_draft_and_active(self, test_session_scope, patch_sync_db):
        async with test_session_scope() as db:
            db.add_all(
                [
                    _skill("d", status="draft", is_active=True),
                    _skill("a", status="active"),
                    _skill("v", status="verified"),
                ]
            )
            await db.flush()

        counts = lifecycle.migrate_legacy_status_rows()
        assert counts["draft_to_pending_review"] == 1
        assert counts["active_to_verified"] == 1

        async with test_session_scope() as db:
            rows = (await db.execute(select(LearnedSkill))).scalars().all()
            st = {r.name: (r.status, r.is_active) for r in rows}
            assert st["d"] == ("pending_review", False)
            assert st["a"] == ("verified", True)
            assert st["v"] == ("verified", True)

    async def test_idempotent(self, test_session_scope, patch_sync_db):
        async with test_session_scope() as db:
            db.add(_skill("d", status="draft"))
            await db.flush()
        lifecycle.migrate_legacy_status_rows()
        counts = lifecycle.migrate_legacy_status_rows()
        assert counts["draft_to_pending_review"] == 0
        assert counts["active_to_verified"] == 0


class TestRepairStateSnapshotEncoding:
    async def test_repairs_only_double_encoded(self, test_session_scope, patch_sync_db):
        async with test_session_scope() as db:
            db.add_all(
                [
                    _trace_event(1, {"a": 1}),
                    _trace_event(2, json.dumps({"b": 2})),
                    _trace_event(3, "not-json{"),
                    _trace_event(4, json.dumps("plain-string")),
                ]
            )
            await db.flush()

        repaired = lifecycle.repair_state_snapshot_encoding()
        assert repaired == 1

        async with test_session_scope() as db:
            rows = (await db.execute(select(TraceEvent))).scalars().all()
            snap = {r.step_number: r.state_snapshot for r in rows}
            assert snap[1] == {"a": 1}
            assert snap[2] == {"b": 2}
            assert snap[3] == "not-json{"
            # json that decodes to a non-dict is left untouched (not a repair)
            assert snap[4] == '"plain-string"'


class TestDropLegacyLearningTables:
    def test_noop_when_no_legacy_tables(self, patch_sync_db):
        assert lifecycle.drop_legacy_learning_tables() == []

    def test_drops_legacy_tables(self, sync_db_engine, patch_sync_db):
        with sync_db_engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS synthesis_jobs (id INTEGER)")
            conn.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS router_training_data (id INTEGER)"
            )
        dropped = lifecycle.drop_legacy_learning_tables()
        assert set(dropped) == {"synthesis_jobs", "router_training_data"}
        # idempotent
        assert lifecycle.drop_legacy_learning_tables() == []

    def test_noop_when_engine_none(self, monkeypatch):
        monkeypatch.setattr(
            dbmod, "db_resource_manager", SimpleNamespace(sync_engine=None)
        )
        assert lifecycle.drop_legacy_learning_tables() == []
