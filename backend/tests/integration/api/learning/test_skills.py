# ruff: noqa: ARG001
"""Integration tests for the /skills API routes (app/api/routes/learning/skills.py)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _mock_session_scope(monkeypatch):
    class FakeDb:
        async def flush(self):
            return None

        async def commit(self):
            return None

        async def add(self, *args, **kwargs):
            return None

        async def refresh(self, *args, **kwargs):
            return None

        async def execute(self, *args, **kwargs):
            return None

        async def get(self, *args, **kwargs):
            return None

    @asynccontextmanager
    async def _fake_scope():
        yield FakeDb()

    monkeypatch.setattr("app.api.routes.learning.skills.session_scope", _fake_scope)


def _make_skill(skill_id=1, **overrides):
    defaults = {
        "id": skill_id,
        "name": "test-skill",
        "description": "A test skill",
        "namespace": "test",
        "trigger_patterns": "[]",
        "parameters": "[]",
        "preconditions": "[]",
        "tools_used": "[]",
        "success_count": 0,
        "failure_count": 0,
        "is_active": True,
        "status": "active",
        "macro_id": None,
        "validation_report": None,
        "instructions": "Do something",
        "resource_path": None,
        "source_thread_id": None,
        "source_session_id": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture(autouse=True)
def _mock_discovery(monkeypatch):
    async def _sync():
        return None

    async def _reload():
        return None

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_discovery.ensure_system_skills_synced",
        _sync,
    )
    monkeypatch.setattr("app.api.routes.learning.skills.skill_discovery.reload", _reload)


async def _no_publish(*args, **kwargs):
    return None


# ── list_skills ──────────────────────────────────────────────────────
async def test_list_skills(client, monkeypatch):
    async def _list_page(**kwargs):
        return [_make_skill(1), _make_skill(2)], 2

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.list_page", _list_page
    )
    resp = await client.get("/learning/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["data"]) == 2


async def test_list_skills_empty(client, monkeypatch):
    async def _list_page(**kwargs):
        return [], 0

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.list_page", _list_page
    )
    resp = await client.get("/learning/skills")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ── get_skill ────────────────────────────────────────────────────────
async def test_get_skill(client, monkeypatch):
    async def _get_by_id(sid, **kwargs):
        return _make_skill(sid)

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.get_by_id", _get_by_id
    )
    resp = await client.get("/learning/skills/3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 3
    assert data["name"] == "test-skill"


async def test_get_skill_404(client, monkeypatch):
    async def _get_by_id(sid, **kwargs):
        return None

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.get_by_id", _get_by_id
    )
    resp = await client.get("/learning/skills/999")
    assert resp.status_code == 404


# ── delete_skill ─────────────────────────────────────────────────────
async def test_delete_skill(client, monkeypatch):
    async def _del(db, sid, mid):
        return _make_skill(sid)

    monkeypatch.setattr("app.api.routes.learning.skills.delete_skill_record", _del)
    monkeypatch.setattr(
        "app.api.routes.learning.skills.publish_skill_mutated", _no_publish
    )
    resp = await client.delete("/learning/skills/5")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


async def test_delete_skill_404(client, monkeypatch):
    from app.core.learning.skills.lifecycle import SkillNotFoundError

    async def _raise(db, sid, mid):
        raise SkillNotFoundError(f"Skill {sid} not found")

    monkeypatch.setattr("app.api.routes.learning.skills.delete_skill_record", _raise)
    resp = await client.delete("/learning/skills/999")
    assert resp.status_code == 404


# ── update_skill ─────────────────────────────────────────────────────
async def test_update_skill(client, monkeypatch):
    async def _update(db, sid, mid, **kwargs):
        return _make_skill(sid, name=kwargs.get("name") or "test-skill")

    async def _load_macro(mid, db=None):
        return None

    monkeypatch.setattr("app.api.routes.learning.skills.update_skill_record", _update)
    monkeypatch.setattr(
        "app.api.routes.learning.skills.publish_skill_mutated", _no_publish
    )
    monkeypatch.setattr("app.api.routes.learning.skills.load_macro", _load_macro)
    resp = await client.put("/learning/skills/5", json={"name": "renamed"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


async def test_update_skill_404(client, monkeypatch):
    from app.core.learning.skills.lifecycle import SkillNotFoundError

    async def _raise(db, sid, mid, **kwargs):
        raise SkillNotFoundError(f"Skill {sid} not found")

    monkeypatch.setattr("app.api.routes.learning.skills.update_skill_record", _raise)
    resp = await client.put("/learning/skills/999", json={"name": "x"})
    assert resp.status_code == 404


async def test_update_skill_conflict(client, monkeypatch):
    from app.core.learning.skills.lifecycle import SkillConflictError

    async def _raise(db, sid, mid, **kwargs):
        raise SkillConflictError("Name already exists")

    monkeypatch.setattr("app.api.routes.learning.skills.update_skill_record", _raise)
    resp = await client.put("/learning/skills/5", json={"name": "dup"})
    assert resp.status_code == 400


# ── run_skill (execute) ──────────────────────────────────────────────
async def test_run_skill_macro_engine(client, monkeypatch):
    skill = _make_skill(10, macro_id=7)

    async def _get_by_id(sid, db=None, **kwargs):
        return skill if sid == 10 else None

    async def _load_macro(mid, db=None):
        return SimpleNamespace(macro_script="steps: []", allow_self_healing=False)

    async def _run(*args, **kwargs):
        return SimpleNamespace(status="ok", success=True, message="done")

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.get_by_id", _get_by_id
    )
    monkeypatch.setattr("app.api.routes.learning.skills.load_macro", _load_macro)
    monkeypatch.setattr("app.api.routes.learning.skills.MacroEngine.run", _run)
    resp = await client.post(
        "/learning/skills/10/execute",
        json={"thread_id": "t-1", "params": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["execution_mode"] == "deterministic"


async def test_run_skill_macro_fallback(client, monkeypatch):
    skill = _make_skill(10, macro_id=7)

    async def _get_by_id(sid, db=None, **kwargs):
        return skill if sid == 10 else None

    async def _load_macro(mid, db=None):
        return SimpleNamespace(macro_script="s")

    async def _run(*args, **kwargs):
        return SimpleNamespace(
            status="fallback_required", success=False, message="healing queued"
        )

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.get_by_id", _get_by_id
    )
    monkeypatch.setattr("app.api.routes.learning.skills.load_macro", _load_macro)
    monkeypatch.setattr("app.api.routes.learning.skills.MacroEngine.run", _run)
    resp = await client.post(
        "/learning/skills/10/execute",
        json={"thread_id": "t-1", "params": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


async def test_run_skill_macro_not_routable(client, monkeypatch):
    skill = _make_skill(10, macro_id=7)

    async def _get_by_id(sid, db=None, **kwargs):
        return skill if sid == 10 else None

    async def _load_macro(mid, db=None):
        return SimpleNamespace(macro_script="s")

    async def _run(*args, **kwargs):
        return SimpleNamespace(status="not_routable", success=False, message="no route")

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.get_by_id", _get_by_id
    )
    monkeypatch.setattr("app.api.routes.learning.skills.load_macro", _load_macro)
    monkeypatch.setattr("app.api.routes.learning.skills.MacroEngine.run", _run)
    resp = await client.post(
        "/learning/skills/10/execute",
        json={"thread_id": "t-1", "params": {}},
    )
    assert resp.status_code == 403


async def test_run_skill_404(client, monkeypatch):
    async def _get_by_id(sid, db=None, **kwargs):
        return None

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.get_by_id", _get_by_id
    )
    resp = await client.post(
        "/learning/skills/999/execute",
        json={"thread_id": "t-1", "params": {}},
    )
    assert resp.status_code == 404


async def test_run_skill_missing_params(client, monkeypatch):
    skill = _make_skill(
        10,
        macro_id=None,
        parameters='[{"name": "url", "required": true}]',
    )

    async def _get_by_id(sid, db=None, **kwargs):
        return skill if sid == 10 else None

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.get_by_id", _get_by_id
    )
    resp = await client.post(
        "/learning/skills/10/execute",
        json={"thread_id": "t-1", "params": {}},
    )
    assert resp.status_code == 400


# ── validate_skill ───────────────────────────────────────────────────
async def test_validate_skill(client, monkeypatch):
    skill = _make_skill(5, resource_path="/tmp/skill-folder")

    async def _get_by_id(sid, db=None, **kwargs):
        return skill

    async def _apply(sk, v):
        return None

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.get_by_id", _get_by_id
    )
    monkeypatch.setattr(
        "app.api.routes.learning.skills.SkillValidator.validate_folder",
        lambda fp: SimpleNamespace(model_dump=lambda: {"valid": True}),
    )
    monkeypatch.setattr("app.api.routes.learning.skills.apply_validation_result", _apply)
    resp = await client.get("/learning/skills/5/validate")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


async def test_validate_skill_no_resource_path(client, monkeypatch):
    skill = _make_skill(5, resource_path=None)

    async def _get_by_id(sid, db=None, **kwargs):
        return skill

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.get_by_id", _get_by_id
    )
    resp = await client.get("/learning/skills/5/validate")
    assert resp.status_code == 200
    assert resp.json()["success"] is False


async def test_validate_skill_404(client, monkeypatch):
    async def _get_by_id(sid, db=None, **kwargs):
        return None

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.get_by_id", _get_by_id
    )
    resp = await client.get("/learning/skills/999/validate")
    assert resp.status_code == 404


# ── confirm_skill ────────────────────────────────────────────────────
async def test_confirm_skill(client, monkeypatch):
    skill = _make_skill(3, macro_id=7)

    async def _confirm(db, sid, mid):
        return skill

    async def _confirm_macro(mid, db=None):
        return None

    monkeypatch.setattr("app.api.routes.learning.skills.confirm_skill", _confirm)
    monkeypatch.setattr("app.api.routes.learning.skills.confirm_macro", _confirm_macro)
    monkeypatch.setattr(
        "app.api.routes.learning.skills.publish_skill_mutated", _no_publish
    )
    resp = await client.post("/learning/skills/3/confirm")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


async def test_confirm_skill_404(client, monkeypatch):
    from app.core.learning.skills.lifecycle import SkillNotFoundError

    async def _raise(db, sid, mid):
        raise SkillNotFoundError("not found")

    monkeypatch.setattr("app.api.routes.learning.skills.confirm_skill", _raise)
    resp = await client.post("/learning/skills/999/confirm")
    assert resp.status_code == 404


# ── create_skill_from_yaml ───────────────────────────────────────────
async def test_create_skill_from_yaml(client, monkeypatch):
    async def _dedup(db, name, mid):
        return name

    async def _create_macro(*args, **kwargs):
        return SimpleNamespace(id=7)

    monkeypatch.setattr(
        "app.api.routes.learning.skills.validate_macro_yaml", lambda y: (True, [])
    )
    monkeypatch.setattr(
        "app.api.routes.learning.skills.macro_from_yaml",
        lambda y: [SimpleNamespace(name="step1")],
    )
    monkeypatch.setattr(
        "app.api.routes.learning.skills.derive_parameters_from_macro", lambda y: []
    )
    monkeypatch.setattr("app.api.routes.learning.skills.deduplicate_name", _dedup)
    async def _create_from_synthesis(db, *args, **kwargs):
        return _make_skill(7, name=kwargs.get("name", "yaml-skill"))

    monkeypatch.setattr(
        "app.api.routes.learning.skills.create_from_synthesis", _create_from_synthesis
    )
    monkeypatch.setattr(
        "app.core.learning.macro.service.MacroService.create_for_skill", _create_macro
    )
    monkeypatch.setattr(
        "app.api.routes.learning.skills.publish_skill_mutated", _no_publish
    )
    monkeypatch.setattr(
        "app.api.routes.learning.skills.publish_macro_mutated", _no_publish
    )
    resp = await client.post(
        "/learning/skills/from-yaml",
        json={"name": "yaml-skill", "yaml_content": "steps:\n  - name: s1\n"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["step_count"] == 1


async def test_create_skill_from_yaml_invalid(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.skills.validate_macro_yaml",
        lambda y: (False, ["bad yaml"]),
    )
    resp = await client.post(
        "/learning/skills/from-yaml",
        json={"name": "bad", "yaml_content": "broken: [["},
    )
    # BUG(known): skills.py:518-520 用 `except Exception` 把自身抛出的
    # HTTPException(400) 重包成 500，前端永远收不到 4xx 语义。当前返回 500，
    # 期望应为 400 —— 见 tests/integration/api/test_known_bugs.py。
    assert resp.status_code == 400


# ── validate_skill_yaml ──────────────────────────────────────────────
async def test_validate_skill_yaml_valid(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.skills.validate_macro_yaml", lambda y: (True, [])
    )
    monkeypatch.setattr(
        "app.api.routes.learning.skills.macro_from_yaml",
        lambda y: [SimpleNamespace(), SimpleNamespace()],
    )
    resp = await client.post(
        "/learning/skills/validate-yaml",
        json={"yaml_content": "steps:\n  - name: a\n  - name: b\n"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["step_count"] == 2


async def test_validate_skill_yaml_invalid(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.skills.validate_macro_yaml",
        lambda y: (False, ["parse error"]),
    )
    resp = await client.post(
        "/learning/skills/validate-yaml",
        json={"yaml_content": "broken"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert "parse error" in data["errors"]


# ── get_skill_yaml ───────────────────────────────────────────────────
async def test_get_skill_yaml_with_macro(client, monkeypatch):
    skill = _make_skill(5, macro_id=7)

    async def _get_by_id(sid, db=None, **kwargs):
        return skill

    async def _load_macro(mid, db=None):
        return SimpleNamespace(macro_script="steps: []")

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.get_by_id", _get_by_id
    )
    monkeypatch.setattr("app.api.routes.learning.skills.load_macro", _load_macro)
    resp = await client.get("/learning/skills/5/yaml")
    assert resp.status_code == 200
    assert resp.text == "steps: []"


async def test_get_skill_yaml_no_macro(client, monkeypatch):
    skill = _make_skill(5, macro_id=None)

    async def _get_by_id(sid, db=None, **kwargs):
        return skill

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.get_by_id", _get_by_id
    )
    resp = await client.get("/learning/skills/5/yaml")
    assert resp.status_code == 200
    assert "No macro" in resp.text


async def test_get_skill_yaml_404(client, monkeypatch):
    async def _get_by_id(sid, db=None, **kwargs):
        return None

    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.get_by_id", _get_by_id
    )
    resp = await client.get("/learning/skills/999/yaml")
    assert resp.status_code == 404


# ── update_skill_yaml ────────────────────────────────────────────────
async def test_update_skill_yaml(client, monkeypatch):
    skill = _make_skill(5)

    async def _get_by_id(sid, db=None, **kwargs):
        return skill

    async def _reconcile(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.api.routes.learning.skills.validate_macro_yaml", lambda y: (True, [])
    )
    monkeypatch.setattr(
        "app.api.routes.learning.skills.macro_from_yaml",
        lambda y: [SimpleNamespace(), SimpleNamespace()],
    )
    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.get_by_id", _get_by_id
    )
    monkeypatch.setattr(
        "app.core.learning.macro.service.MacroService.reconcile_for_skill", _reconcile
    )
    monkeypatch.setattr(
        "app.api.routes.learning.skills.publish_skill_mutated", _no_publish
    )
    resp = await client.put(
        "/learning/skills/5/yaml",
        content="steps:\n  - name: a\n  - name: b\n",
        headers={"Content-Type": "text/yaml"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["step_count"] == 2


async def test_update_skill_yaml_invalid(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.learning.skills.validate_macro_yaml", lambda y: (False, ["bad"])
    )
    resp = await client.put(
        "/learning/skills/5/yaml",
        content="broken",
        headers={"Content-Type": "text/yaml"},
    )
    # BUG(known): skills.py:600-602 用 `except Exception` 把自身抛出的
    # HTTPException(400) 重包成 500，当前返回 500，期望应为 400。
    assert resp.status_code == 400


async def test_update_skill_yaml_404(client, monkeypatch):
    async def _get_by_id(sid, db=None, **kwargs):
        return None

    monkeypatch.setattr(
        "app.api.routes.learning.skills.validate_macro_yaml", lambda y: (True, [])
    )
    monkeypatch.setattr("app.api.routes.learning.skills.macro_from_yaml", lambda y: [])
    monkeypatch.setattr(
        "app.api.routes.learning.skills.skill_repository.get_by_id", _get_by_id
    )
    resp = await client.put(
        "/learning/skills/999/yaml",
        content="steps: []",
        headers={"Content-Type": "text/yaml"},
    )
    # BUG(known): skills.py:600-602 把自身抛出的 HTTPException(404) 重包成 500，
    # 当前返回 500，期望应为 404。
    assert resp.status_code == 404


# ── import_skills ────────────────────────────────────────────────────
async def test_import_skills(client, monkeypatch):
    async def _import(directory):
        return SimpleNamespace(model_dump=lambda: {"imported": 2})

    monkeypatch.setattr(
        "app.api.routes.learning.skills.SkillImporter.import_from_directory", _import
    )
    resp = await client.post(
        "/learning/skills/import", json={"directory": "/tmp/skills"}
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ── synthesize_skill ─────────────────────────────────────────────────
async def test_synthesize_skill(client, monkeypatch):
    fake_skill_dto = SimpleNamespace(
        name="synth",
        description="synthesized",
        trigger_patterns=["t"],
        parameters=[],
        preconditions=[],
        tools_used=[],
        source_thread_id="t1",
        source_session_id=None,
        instructions="do it",
        to_yaml=lambda: "name: synth\n",
    )
    synth_result = SimpleNamespace(skill=fake_skill_dto)

    async def _parse():
        return []

    async def _synthesize():
        return synth_result

    async def _create_from_synthesis(db, **kwargs):
        return _make_skill(10, name=kwargs.get("name", "synth"))

    async def _create_macro(*args, **kwargs):
        return SimpleNamespace(id=20)

    monkeypatch.setattr(
        "app.api.routes.learning.skills.TraceParser",
        lambda tid, sid: SimpleNamespace(parse=_parse),
    )
    monkeypatch.setattr(
        "app.api.routes.learning.skills.WorkflowSynthesizer",
        lambda tid, sid, sequence: SimpleNamespace(synthesize=_synthesize),
    )
    monkeypatch.setattr(
        "app.api.routes.learning.skills.MacroScriptCompiler",
        lambda: SimpleNamespace(
            compile=lambda s: SimpleNamespace(to_yaml=lambda: "steps: []")
        ),
    )
    monkeypatch.setattr(
        "app.api.routes.learning.skills.create_from_synthesis", _create_from_synthesis
    )
    monkeypatch.setattr(
        "app.core.learning.macro.service.MacroService.create_for_skill", _create_macro
    )
    monkeypatch.setattr(
        "app.api.routes.learning.skills.publish_skill_mutated", _no_publish
    )
    monkeypatch.setattr(
        "app.api.routes.learning.skills.publish_macro_mutated", _no_publish
    )
    resp = await client.post(
        "/learning/skills/synthesize",
        json={"thread_id": "t1", "session_id": "s1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["skill_id"] == 10
    assert data["skill_name"] == "synth"
