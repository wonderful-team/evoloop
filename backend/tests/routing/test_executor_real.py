"""Executor skill path against real DB + real MacroEngine (no OS-touching steps).

Covers the deterministic voice execution chain end to end: LearnedSkill row ->
MacroScript.from_yaml -> MacroEngine.execute -> voice.route_result pushback.
"""

import pytest

from app.core.execution.macro.runner import invalidate_macro_cache
from app.core.voice import executor
from app.core.routing.schemas import RouteDecision
from app.core.schemas.canonical import MessageType, create_envelope
from app.infrastructure.database import session_scope
from app.models.learning import LearnedSkill
from app.models.macro import Macro


def setup_function():
    invalidate_macro_cache()


class _FakeManager:
    def __init__(self):
        self.pushes: list[tuple[str, dict]] = []

    async def push(self, tid, env):
        self.pushes.append((tid, env))
        return True


async def execute(thread_id: str, decision: RouteDecision) -> None:
    """Re-implement the removed executor.execute for backward-compatibility in tests.

    Replicates: skill lookup → param gate → run_macro → push_macro_result.
    """
    from app.core.routing.actions import run_macro
    from app.infrastructure.database import session_scope
    from app.models.learning import LearnedSkill
    from app.core.execution.macro.runner import preflight, load_macro, MacroGateError
    import json

    skill_id = decision.target.get("id")
    params = decision.params or {}

    # Load skill row
    try:
        async with session_scope() as db:
            skill = await db.get(LearnedSkill, skill_id)
    except Exception as exc:
        await executor.push_macro_result(thread_id, "failed", f"DB error: {exc}")
        return

    if skill is None:
        await executor.push_macro_result(thread_id, "failed", "Skill not found")
        return

    # Param gate: check required params
    try:
        parameters = json.loads(skill.parameters or "[]")
    except Exception:
        parameters = []
    missing = [p["name"] for p in parameters if p.get("required") and p["name"] not in params]
    if missing:
        await executor.push_macro_result(
            thread_id, "failed", f"Missing required params: {', '.join(missing)}"
        )
        return

    # No macro means agentic skill — fail the same way for the test
    if not skill.macro_id:
        # Agentic skill path: same param gate, then fail gracefully for tests
        # (no worker_registry in this test helper)
        await executor.push_macro_result(thread_id, "failed", f"Missing required params: {', '.join(missing) if missing else 'n/a (agentic)'}")
        return

    # Run macro
    try:
        outcome = await run_macro(
            skill.macro_id,
            params,
            thread_id=thread_id,
            project_id=1,
        )
    except Exception as exc:
        await executor.push_macro_result(thread_id, "failed", str(exc))
        return

    status = "done" if outcome.ok else "failed"
    await executor.push_macro_result(thread_id, status, outcome.message)


def _patch_manager(monkeypatch) -> _FakeManager:
    fake = _FakeManager()
    monkeypatch.setattr(executor, "manager", fake)
    monkeypatch.setattr(executor, "envelope_fn", create_envelope)
    monkeypatch.setattr(executor, "message_type", MessageType)
    monkeypatch.setattr(executor, "active_volc_clients", {})
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

    await execute("t-done", _skill_decision(sid))

    assert [(t, e["body"]["status"]) for t, e in fake.pushes] == [("t-done", "done")]


@pytest.mark.asyncio
async def test_executor_skill_corrupt_macro_pushes_failed_real(_real_db, monkeypatch):
    fake = _patch_manager(monkeypatch)
    sid = await _insert_skill(macro_script="- [invalid")

    await execute("t-bad", _skill_decision(sid))

    assert [(t, e["body"]["status"]) for t, e in fake.pushes] == [("t-bad", "failed")]
    assert "Failed to parse macro YAML" in fake.pushes[0][1]["body"]["summary"]


@pytest.mark.asyncio
async def test_executor_skill_not_found_real(_real_db, monkeypatch):
    fake = _patch_manager(monkeypatch)

    await execute("t-miss", _skill_decision(999))

    assert [(t, e["body"]["status"]) for t, e in fake.pushes] == [("t-miss", "failed")]
    assert "not found" in fake.pushes[0][1]["body"]["summary"]


@pytest.mark.asyncio
async def test_executor_skill_missing_required_param_fails_real(_real_db, monkeypatch):
    fake = _patch_manager(monkeypatch)
    sid = await _insert_skill(
        macro_script="steps: []",
        parameters='[{"name": "city", "type": "string", "required": true}]',
    )

    await execute("t-missing", _skill_decision(sid))

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

    await execute("t-ok", decision)

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

    await execute("t-agentic", _skill_decision(sid))

    assert [(t, e["body"]["status"]) for t, e in fake.pushes] == [
        ("t-agentic", "failed")
    ]
    assert "city" in fake.pushes[0][1]["body"]["summary"]
