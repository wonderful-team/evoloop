"""Executor skill path against real DB + real MacroEngine (no OS-touching steps).

Covers the deterministic voice execution chain end to end: LearnedSkill row ->
MacroScript.from_yaml -> MacroEngine.execute -> voice.route_result pushback.
"""

import pytest

from app.core.routing import executor
from app.core.routing.schemas import RouteDecision
from app.infrastructure.database import session_scope
from app.models.learning import LearnedSkill
from app.models.macro import Macro


class _FakeManager:
    def __init__(self):
        self.pushes: list[tuple[str, dict]] = []

    async def push(self, tid, env):
        self.pushes.append((tid, env))
        return True


def _patch_manager(monkeypatch) -> _FakeManager:
    fake = _FakeManager()
    monkeypatch.setattr(executor, "manager", fake)
    return fake


async def _insert_skill(**kwargs) -> int:
    async with session_scope() as db:
        macro_script = kwargs.pop("macro_script", None)
        parameters = kwargs.pop("parameters", "[]")
        kwargs.pop("execution_mode", None)
        skill = LearnedSkill(
            name=kwargs.pop("name", "s"),
            description="",
            trigger_patterns="[]",
            parameters=parameters,
            status=kwargs.pop("status", "verified"),
            is_active=kwargs.pop("is_active", True),
            **kwargs,
        )
        db.add(skill)
        await db.flush()
        if macro_script is not None:
            macro = Macro(
                name=skill.name,
                description="",
                trigger_patterns=[],
                parameters=skill.parameters or [],
                macro_script=macro_script,
                status=skill.status,
                is_active=skill.is_active,
                fallback_skill_id=skill.id,
                member_id=skill.member_id,
            )
            db.add(macro)
            await db.flush()
            skill.macro_id = macro.id
            await db.flush()
        return skill.id


def _skill_decision(sid: int) -> RouteDecision:
    return RouteDecision(
        status="routed",
        target_type="skill",
        target={"type": "skill", "id": sid},
        params={},
    )


@pytest.mark.asyncio
async def test_executor_skill_deterministic_done_real(_real_db, monkeypatch):
    fake = _patch_manager(monkeypatch)
    sid = await _insert_skill(macro_script="steps: []")

    await executor.execute("t-done", _skill_decision(sid))

    assert [(t, e["body"]["status"]) for t, e in fake.pushes] == [("t-done", "done")]


@pytest.mark.asyncio
async def test_executor_skill_corrupt_macro_pushes_failed_real(_real_db, monkeypatch):
    fake = _patch_manager(monkeypatch)
    sid = await _insert_skill(macro_script="- [invalid")

    await executor.execute("t-bad", _skill_decision(sid))

    assert [(t, e["body"]["status"]) for t, e in fake.pushes] == [("t-bad", "failed")]
    assert "Failed to parse macro YAML" in fake.pushes[0][1]["body"]["summary"]


@pytest.mark.asyncio
async def test_executor_skill_not_found_real(_real_db, monkeypatch):
    fake = _patch_manager(monkeypatch)

    await executor.execute("t-miss", _skill_decision(999))

    assert [(t, e["body"]["status"]) for t, e in fake.pushes] == [("t-miss", "failed")]
    assert "not found" in fake.pushes[0][1]["body"]["summary"]


@pytest.mark.asyncio
async def test_executor_skill_missing_required_param_fails_real(_real_db, monkeypatch):
    fake = _patch_manager(monkeypatch)
    sid = await _insert_skill(
        macro_script="steps: []",
        parameters='[{"name": "city", "type": "string", "required": true}]',
    )

    await executor.execute("t-missing", _skill_decision(sid))

    assert [(t, e["body"]["status"]) for t, e in fake.pushes] == [
        ("t-missing", "failed")
    ]
    assert "city" in fake.pushes[0][1]["body"]["summary"]


@pytest.mark.asyncio
async def test_executor_skill_required_param_present_runs_real(_real_db, monkeypatch):
    fake = _patch_manager(monkeypatch)
    sid = await _insert_skill(
        macro_script="steps: []",
        parameters='[{"name": "city", "type": "string", "required": true}]',
    )
    decision = RouteDecision(
        status="routed",
        target_type="skill",
        target={"type": "skill", "id": sid},
        params={"city": "Paris"},
    )

    await executor.execute("t-ok", decision)

    assert [(t, e["body"]["status"]) for t, e in fake.pushes] == [("t-ok", "done")]


@pytest.mark.asyncio
async def test_executor_agentic_skill_missing_required_param_fails_real(
    _real_db, monkeypatch
):
    """The param gate applies before the mode branch, matching REST execute."""
    fake = _patch_manager(monkeypatch)
    sid = await _insert_skill(
        macro_script=None,
        parameters='[{"name": "city", "type": "string", "required": true}]',
    )

    await executor.execute("t-agentic", _skill_decision(sid))

    assert [(t, e["body"]["status"]) for t, e in fake.pushes] == [
        ("t-agentic", "failed")
    ]
    assert "city" in fake.pushes[0][1]["body"]["summary"]
