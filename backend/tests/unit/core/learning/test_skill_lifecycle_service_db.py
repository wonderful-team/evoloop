"""Tests for the single skill creation service (app.core.learning).

Pure helpers (parameter derivation/normalization) plus real-SQLite tests for
name dedup and create_from_synthesis, which owns the (pending_review,
is_active=False) pair for every synthesis-style creation path.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.core.learning.schemas import SkillParameter
from app.core.learning.skill_lifecycle import (
    create_from_synthesis,
    deduplicate_name,
    migrate_legacy_status_rows,
    repair_state_snapshot_encoding,
)
from app.infrastructure.database import session_scope
from app.models.learning import LearnedSkill, TraceEvent
from app.utils.parameters import (
    derive_parameters_from_macro,
    normalize_parameters,
)

_MACRO_WITH_PARAMS = """steps:
  - step_number: 1
    type: open_app
    payload:
      app: "{{ app }}"
      note: "{{ user.note }}"
      again: "{{app}}"
"""


class TestDeriveParameters:
    def test_none_macro_returns_empty(self):
        assert derive_parameters_from_macro(None) == []

    def test_no_placeholders_returns_empty(self):
        assert derive_parameters_from_macro("steps:\n  - type: dump\n") == []

    def test_extracts_unique_root_names_sorted(self):
        params = derive_parameters_from_macro(_MACRO_WITH_PARAMS)
        assert [p["name"] for p in params] == ["app", "user"]
        assert all(p["required"] is True for p in params)
        assert all(p["type"] == "string" for p in params)


class TestNormalizeParameters:
    def test_none_and_garbage(self):
        assert normalize_parameters(None) == []
        assert normalize_parameters("not json") == []
        assert normalize_parameters({"a": 1}) == []

    def test_skill_parameter_objects(self):
        out = normalize_parameters([SkillParameter(name="app", required=True)])
        assert out == [
            {
                "name": "app",
                "type": "string",
                "description": "",
                "required": True,
                "default": None,
            }
        ]

    def test_dicts_and_json_string(self):
        out = normalize_parameters(json.dumps([{"name": "k", "type": "int"}]))
        assert out[0]["name"] == "k"
        assert out[0]["type"] == "int"

    def test_items_without_name_dropped(self):
        assert normalize_parameters([{"type": "string"}, "junk", None]) == []


async def _insert_skill(**kwargs) -> int:
    async with session_scope() as db:
        kwargs.setdefault("name", "s")
        kwargs.setdefault("description", "")
        kwargs.setdefault("trigger_patterns", "[]")
        kwargs.setdefault("parameters", "[]")
        skill = LearnedSkill(**kwargs)
        db.add(skill)
        await db.flush()
        return skill.id


@pytest.mark.asyncio
async def test_deduplicate_name_suffixes(_real_db):
    await _insert_skill(name="dup")
    await _insert_skill(name="dup_1")
    async with session_scope() as db:
        assert await deduplicate_name(db, "free", 0) == "free"
        assert await deduplicate_name(db, "dup", 0) == "dup_2"


@pytest.mark.asyncio
async def test_create_from_synthesis_writes_pending_pair_and_normalizes(_real_db):
    async with session_scope() as db:
        skill = await create_from_synthesis(
            db,
            name="new_skill",
            member_id=7,
            description="d",
            trigger_patterns=["打开"],
            parameters=[SkillParameter(name="app", required=True)],
            skill_source="record",
        )
        skill_id = skill.id

    async with session_scope() as db:
        row = (
            await db.execute(select(LearnedSkill).where(LearnedSkill.id == skill_id))
        ).scalar_one()
        assert row.member_id == 7
        assert row.status == "pending_review"
        assert row.is_active is False
        assert row.trigger_patterns == ["打开"]
        assert row.parameters[0]["name"] == "app"
        assert row.skill_source == "record"
        assert row.macro_id is None


@pytest.mark.asyncio
async def test_create_from_synthesis_dedups_name(_real_db):
    await _insert_skill(name="taken")
    async with session_scope() as db:
        skill = await create_from_synthesis(db, name="taken")
    assert skill.name == "taken_1"


@pytest.mark.asyncio
async def test_migrate_legacy_status_rows_repairs_and_is_idempotent(_real_db):
    """Pre-convergence rows: draft+active (silently unroutable, unconfirmable)
    -> pending_review+inactive (confirmable); status 'active' -> verified so
    the tightened routable set {verified} keeps them routed."""
    await _insert_skill(name="draft_row", status="draft", is_active=True)
    await _insert_skill(name="active_row", status="active", is_active=True)
    await _insert_skill(name="verified_row", status="verified", is_active=True)
    await _insert_skill(name="pending_row", status="pending_review", is_active=False)

    counts = migrate_legacy_status_rows()
    assert counts == {"draft_to_pending_review": 1, "active_to_verified": 1}

    async with session_scope() as db:
        rows = {
            r.name: (r.status, r.is_active)
            for r in (await db.execute(select(LearnedSkill))).scalars().all()
        }
    assert rows["draft_row"] == ("pending_review", False)
    assert rows["active_row"] == ("verified", True)
    assert rows["verified_row"] == ("verified", True)
    assert rows["pending_row"] == ("pending_review", False)

    # Idempotent: a second pass touches nothing.
    assert migrate_legacy_status_rows() == {
        "draft_to_pending_review": 0,
        "active_to_verified": 0,
    }


@pytest.mark.asyncio
async def test_drop_legacy_learning_tables_drops_and_is_idempotent(_real_db):
    """Startup cleanup for removed learning tables: drops orphans when
    present, no-op (empty list) on subsequent runs."""
    from sqlalchemy import inspect, text

    from app.core.learning.skill_lifecycle import (
        drop_legacy_learning_tables,
    )
    from app.infrastructure.database.sql.database import db_resource_manager

    engine = db_resource_manager.sync_engine
    assert engine is not None
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS synthesis_jobs (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS router_training_data (id INTEGER PRIMARY KEY)"))

    assert sorted(drop_legacy_learning_tables()) == ["router_training_data", "synthesis_jobs"]
    remaining = inspect(engine).get_table_names()
    assert "synthesis_jobs" not in remaining
    assert "router_training_data" not in remaining
    assert drop_legacy_learning_tables() == []


@pytest.mark.asyncio
async def test_repair_state_snapshot_encoding_fixes_only_legacy_rows(_real_db):
    """Legacy rows hold a json.dumps string in the JSON column (the ORM stores
    an assigned str as a JSON string, reproducing the legacy shape exactly);
    dict/None rows are untouched and the pass is idempotent."""
    async with session_scope() as db:
        db.add(
            TraceEvent(
                member_id=0, thread_id="t", step_number=0, node_name="n",
                event_type="click", payload={},
                state_snapshot=json.dumps({"context": "dom_recorder"}),
            )
        )
        db.add(
            TraceEvent(
                member_id=0, thread_id="t", step_number=1, node_name="n",
                event_type="click", payload={},
                state_snapshot={"context": "ok"},
            )
        )
        db.add(
            TraceEvent(
                member_id=0, thread_id="t", step_number=2, node_name="n",
                event_type="click", payload={}, state_snapshot=None,
            )
        )

    assert repair_state_snapshot_encoding() == 1

    async with session_scope() as db:
        rows = {
            r.step_number: r.state_snapshot
            for r in (await db.execute(select(TraceEvent))).scalars().all()
        }
    assert rows[0] == {"context": "dom_recorder"}
    assert rows[1] == {"context": "ok"}
    assert rows[2] is None

    assert repair_state_snapshot_encoding() == 0


def _write_skill_md(folder, name: str, description: str = "d") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n# SOP\ndo it\n"
    )


@pytest.mark.asyncio
async def test_importer_preserves_pending_review_on_reimport(_real_db, tmp_path):
    """A synthesized skill awaiting user confirmation must NOT be touched at
    all when the file watcher re-imports its exported SKILL.md — status,
    activation, and all content fields are owned by the synthesis route."""
    from app.core.learning.skill_importer import SkillImporter

    await _insert_skill(name="watcher_skill", status="pending_review", is_active=False)
    folder = tmp_path / "watcher_skill"
    _write_skill_md(folder, "watcher_skill", description="updated from disk")

    assert await SkillImporter.import_single_skill(folder) is True

    async with session_scope() as db:
        skill = (
            await db.execute(select(LearnedSkill).where(LearnedSkill.name == "watcher_skill"))
        ).scalar_one()
        assert skill.status == "pending_review"
        assert skill.is_active is False
        assert skill.description != "updated from disk"


@pytest.mark.asyncio
async def test_importer_update_restores_legal_pair_for_non_pending(_real_db, tmp_path):
    """Update path must keep the (status, is_active) pair legal: any
    non-pending status the importer writes implies is_active=True."""
    from app.core.learning.skill_importer import SkillImporter

    await _insert_skill(name="legacy_pair", status="candidate", is_active=False)
    folder = tmp_path / "legacy_pair"
    _write_skill_md(folder, "legacy_pair")

    assert await SkillImporter.import_single_skill(folder) is True

    async with session_scope() as db:
        skill = (
            await db.execute(select(LearnedSkill).where(LearnedSkill.name == "legacy_pair"))
        ).scalar_one()
        assert skill.status in ("verified", "candidate")
        assert skill.is_active is True
