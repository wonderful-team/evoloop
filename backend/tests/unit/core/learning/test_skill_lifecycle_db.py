"""Skill route handlers against a real SQLite DB.

Replaces the mock-session version (test_skill_lifecycle_current.py): handlers
run against real session_scope + real rows; only true external boundaries are
stubbed (synthesizers/LLM, SkillValidator, event publisher, skill discovery,
video file existence).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.routes.learning import skills as skill_routes
from app.api.routes.learning import synthesis as synthesis_routes
from app.core.learning.schemas import SkillExecutionParams, SkillParameter
from app.core.learning.schemas.requests import (
    CreateSkillFromYamlRequest,
    ExecuteSkillRequest,
    SynthesizeFromRecordingRequest,
    SynthesizeRequest,
)
from app.core.learning.workflow_synthesizer import SynthesisResult, SynthesizedSkill
from app.core.learning.trace_parser import TraceSequence
from app.infrastructure.database import session_scope
from app.models.learning import LearnedSkill
from app.models.macro import Macro

_DUMP_YAML = """steps:
  - step_number: 1
    type: dump
    payload:
      path: /tmp/x.json
"""


def _discovery_stub():
    stub = MagicMock()
    stub.reload = AsyncMock()
    stub.ensure_system_skills_synced = AsyncMock()
    return stub


def _fake_sequence():
    from app.core.learning.trace_parser import TraceSequence
    return TraceSequence(thread_id="t1", steps=[])


def _fake_macro_compiler():
    fake = MagicMock()
    fake.compile.return_value.to_yaml.return_value = _DUMP_YAML
    return fake


async def _get_skill(skill_id: int) -> LearnedSkill | None:
    async with session_scope() as db:
        return await db.get(LearnedSkill, skill_id)


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


async def _link_macro(skill_id: int, macro_script: str = _DUMP_YAML) -> int:
    async with session_scope() as db:
        skill = await db.get(LearnedSkill, skill_id)
        macro = Macro(
            name=skill.name,
            description=skill.description or "",
            trigger_patterns=skill.trigger_patterns or [],
            parameters=skill.parameters or [],
            macro_script=macro_script,
            status="verified" if skill.status == "verified" else "pending_review",
            is_active=skill.is_active and skill.status == "verified",
            fallback_skill_id=skill.id,
            member_id=skill.member_id,
        )
        db.add(macro)
        await db.flush()
        skill.macro_id = macro.id
        await db.flush()
        return macro.id


async def _get_macro(macro_id: int) -> Macro | None:
    async with session_scope() as db:
        return await db.get(Macro, macro_id)


@pytest.mark.asyncio
async def test_synthesize_persists_pending_review_inactive(_real_db):
    synthesized = SynthesisResult(
        skill=SynthesizedSkill(
            name="open_wechat",
            description="Open WeChat",
            trigger_patterns=["打开微信"],
            parameters=[SkillParameter(name="app", required=True)],
            tools_used=["desktop_control"],
            source_thread_id="t1",
        ),
    )
    fake_synth = MagicMock()
    fake_synth.synthesize = AsyncMock(return_value=synthesized)

    with (
        patch(
            "app.api.routes.learning.skills.TraceParser",
            MagicMock(return_value=MagicMock(parse=AsyncMock(return_value=_fake_sequence()))),
        ),
        patch(
            "app.api.routes.learning.skills.MacroScriptCompiler",
            MagicMock(return_value=_fake_macro_compiler()),
        ),
        patch(
            "app.api.routes.learning.skills.WorkflowSynthesizer",
            MagicMock(return_value=fake_synth),
        ),
        patch(
            "app.api.routes.learning.skills.publish_skill_mutated",
            new_callable=AsyncMock,
        ) as mock_pub,
        patch("app.api.routes.learning.skills.skill_discovery", _discovery_stub()),
    ):
        resp = await skill_routes.synthesize_skill(
            SynthesizeRequest(thread_id="t1"),
            current_user=SimpleNamespace(id=7),
        )

    assert resp.success is True
    row = await _get_skill(resp.skill_id)
    assert row is not None
    assert row.member_id == 7
    assert row.status == "pending_review"
    assert row.is_active is False
    assert row.macro_id is not None
    macro = await _get_macro(row.macro_id)
    assert macro is not None
    assert macro.macro_script == _DUMP_YAML
    assert macro.status == "pending_review"
    assert macro.is_active is False
    assert row.parameters[0]["name"] == "app"
    mock_pub.assert_awaited_once_with(skill_id=resp.skill_id, action="create")


@pytest.mark.asyncio
async def test_create_from_yaml_persists_pending_review_inactive(_real_db):
    with (
        patch(
            "app.api.routes.learning.skills.publish_skill_mutated",
            new_callable=AsyncMock,
        ) as mock_pub,
        patch("app.api.routes.learning.skills.skill_discovery", _discovery_stub()),
    ):
        resp = await skill_routes.create_skill_from_yaml(
            CreateSkillFromYamlRequest(name="yaml_skill", yaml_content=_DUMP_YAML),
            MagicMock(),
            current_user=SimpleNamespace(id=0),
        )

    assert resp.success is True
    assert resp.step_count == 1
    row = await _get_skill(resp.skill_id)
    assert row.status == "pending_review"
    assert row.is_active is False
    assert row.macro_id is not None
    macro = await _get_macro(row.macro_id)
    assert macro is not None
    assert macro.macro_script == _DUMP_YAML
    mock_pub.assert_awaited_once_with(skill_id=resp.skill_id, action="create")


@pytest.mark.asyncio
async def test_multimodal_synthesize_persists_pending_review_inactive(_real_db):
    skill_data = {
        "name": "mm_skill",
        "description": "From recording",
        "namespace": "misc",
        "trigger_patterns": ["录制技能"],
        "parameters": [{"name": "target", "required": True}],
        "instructions": "do it",
    }
    fake_synth = MagicMock()
    fake_synth.synthesize = AsyncMock(
        return_value={
            "skill": skill_data,
            "macro_script": None,
            "metadata": {"frames_analyzed": 3, "events_processed": 4},
        }
    )

    with (
        patch("app.api.routes.learning.synthesis.os.path.exists", return_value=True),
        patch(
            "app.api.routes.learning.synthesis.MultimodalSkillSynthesizer",
            MagicMock(return_value=fake_synth),
        ),
        patch(
            "app.api.routes.learning.synthesis.publish_skill_mutated",
            new_callable=AsyncMock,
        ),
    ):
        resp = await synthesis_routes.synthesize_from_recording(
            SynthesizeFromRecordingRequest(
                video_path="/tmp/video.mp4",
                session_id="s1",
                task_description="recorded task",
            ),
            current_user=SimpleNamespace(id=7),
        )

    assert resp.success is True
    row = await _get_skill(resp.skill_id)
    assert row.status == "pending_review"
    assert row.is_active is False
    assert row.skill_source == "multimodal_record"
    assert row.validation_report == {"status": "pending_verification"}


@pytest.mark.asyncio
async def test_create_from_yaml_derives_parameters_from_placeholders(_real_db):
    yaml_with_params = """steps:
  - step_number: 1
    type: open_app
    payload:
      app: "{{ app }}"
"""
    with (
        patch(
            "app.api.routes.learning.skills.publish_skill_mutated",
            new_callable=AsyncMock,
        ),
        patch("app.api.routes.learning.skills.skill_discovery", _discovery_stub()),
    ):
        resp = await skill_routes.create_skill_from_yaml(
            CreateSkillFromYamlRequest(
                name="param_skill", yaml_content=yaml_with_params
            ),
            MagicMock(),
            current_user=SimpleNamespace(id=0),
        )

    row = await _get_skill(resp.skill_id)
    assert [p["name"] for p in row.parameters] == ["app"]
    assert row.parameters[0]["required"] is True


@pytest.mark.asyncio
async def test_execute_pending_review_skill_forbidden(_real_db):
    sid = await _insert_skill(
        status="pending_review",
        is_active=False,
    )
    await _link_macro(sid, macro_script=_DUMP_YAML)

    with pytest.raises(HTTPException) as exc:
        await skill_routes.execute_skill(
            sid,
            ExecuteSkillRequest(thread_id="t1", params=SkillExecutionParams()),
            MagicMock(),
            current_user=SimpleNamespace(id=0),
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_confirm_pending_review_activates(_real_db):
    sid = await _insert_skill(status="pending_review", is_active=False)

    with patch(
        "app.api.routes.learning.skills.publish_skill_mutated", new_callable=AsyncMock
    ) as mock_pub:
        resp = await skill_routes.confirm_learned_skill(
            sid, current_user=SimpleNamespace(id=0)
        )

    assert resp.success is True
    row = await _get_skill(sid)
    assert row.status == "verified"
    assert row.is_active is True
    mock_pub.assert_awaited_once_with(skill_id=sid, action="update")


@pytest.mark.asyncio
async def test_confirm_rejects_non_pending_review(_real_db):
    sid = await _insert_skill(status="candidate", is_active=False)

    with pytest.raises(HTTPException) as exc:
        await skill_routes.confirm_learned_skill(
            sid, current_user=SimpleNamespace(id=0)
        )

    assert exc.value.status_code == 400
    row = await _get_skill(sid)
    assert row.status == "candidate"
    assert row.is_active is False


@pytest.mark.asyncio
async def test_validate_sets_verified_when_healthy(_real_db):
    sid = await _insert_skill(
        status="pending_review", is_active=False, resource_path="/tmp/skill"
    )
    validation = SimpleNamespace(
        status="healthy", model_dump=lambda: {"status": "healthy"}
    )

    with patch(
        "app.api.routes.learning.skills.SkillValidator.validate_folder",
        return_value=validation,
    ):
        resp = await skill_routes.validate_skill(
            sid, current_user=SimpleNamespace(id=0)
        )

    assert resp.success is True
    row = await _get_skill(sid)
    assert row.status == "verified"
    assert row.is_active is True  # legal pair: (verified, True)
    assert row.validation_report == {"status": "healthy"}


@pytest.mark.asyncio
async def test_validate_sets_candidate_when_not_healthy(_real_db):
    sid = await _insert_skill(
        status="pending_review", is_active=False, resource_path="/tmp/skill"
    )
    validation = SimpleNamespace(
        status="warning", model_dump=lambda: {"status": "warning"}
    )

    with patch(
        "app.api.routes.learning.skills.SkillValidator.validate_folder",
        return_value=validation,
    ):
        resp = await skill_routes.validate_skill(
            sid, current_user=SimpleNamespace(id=0)
        )

    assert resp.success is True
    row = await _get_skill(sid)
    assert row.status == "candidate"
    assert row.is_active is True  # legal pair: (candidate, True)


@pytest.mark.asyncio
async def test_execute_deterministic_queues_macro(_real_db):
    sid = await _insert_skill(
        status="verified",
        is_active=True,
    )
    await _link_macro(sid, macro_script=_DUMP_YAML)
    bg_tasks = MagicMock()

    from app.core.execution.macro.runner import ExecutionOutcome

    with patch(
        "app.api.routes.learning.skills.run_deterministic",
        new_callable=AsyncMock,
        return_value=ExecutionOutcome(ok=True, message="done"),
    ) as mock_run:
        resp = await skill_routes.execute_skill(
            sid,
            ExecuteSkillRequest(thread_id="t1", params=SkillExecutionParams()),
            bg_tasks,
            current_user=SimpleNamespace(id=0),
        )

    assert resp.success is True
    assert resp.execution_mode == "deterministic"
    mock_run.assert_awaited_once()
    bg_tasks.add_task.assert_not_called()


@pytest.mark.asyncio
async def test_execute_missing_required_params_rejected(_real_db):
    sid = await _insert_skill(
        status="verified",
        is_active=True,
        parameters=json.dumps([{"name": "app", "required": True}]),
    )
    await _link_macro(sid, macro_script=_DUMP_YAML)

    with pytest.raises(HTTPException) as exc:
        await skill_routes.execute_skill(
            sid,
            ExecuteSkillRequest(thread_id="t1", params=SkillExecutionParams()),
            MagicMock(),
            current_user=SimpleNamespace(id=0),
        )

    assert exc.value.status_code == 400
    assert "app" in exc.value.detail


@pytest.mark.asyncio
async def test_execute_with_required_params_passes(_real_db):
    sid = await _insert_skill(
        status="verified",
        is_active=True,
        parameters=json.dumps([{"name": "app", "required": True}]),
    )
    await _link_macro(sid, macro_script=_DUMP_YAML)
    bg_tasks = MagicMock()

    from app.core.execution.macro.runner import ExecutionOutcome

    with patch(
        "app.api.routes.learning.skills.run_deterministic",
        new_callable=AsyncMock,
        return_value=ExecutionOutcome(ok=True, message="done"),
    ):
        resp = await skill_routes.execute_skill(
            sid,
            ExecuteSkillRequest(
                thread_id="t1", params=SkillExecutionParams(app="wechat")
            ),
            bg_tasks,
            current_user=SimpleNamespace(id=0),
        )

    assert resp.success is True
    bg_tasks.add_task.assert_not_called()


@pytest.mark.asyncio
async def test_list_skills_bootstraps_system_skills_and_filters(_real_db):
    """list_skills triggers the one-time system-skill bootstrap through the
    public discovery API (no private-method call) and honors active_only."""
    await _insert_skill(name="vis", status="verified", is_active=True)
    await _insert_skill(name="hid", status="pending_review", is_active=False)

    stub = _discovery_stub()
    with patch("app.api.routes.learning.skills.skill_discovery", stub):
        active = await skill_routes.list_skills(active_only=True, page=1, page_size=50)
        everything = await skill_routes.list_skills(
            active_only=False, page=1, page_size=50
        )

    assert stub.ensure_system_skills_synced.await_count == 2
    assert {s.name for s in active.data} == {"vis"}
    assert active.total == 1
    assert {s.name for s in everything.data} == {"vis", "hid"}
    assert everything.total == 2


@pytest.mark.asyncio
async def test_multimodal_verification_is_structural_only(_real_db):
    """The synthesis route must NOT execute the macro for verification
    (the engine ignores is_dry_run — execution would drive the user's real
    desktop — and running it inside the create transaction self-deadlocks
    SQLite). validation_report is a structural check: YAML parse +
    MacroScript schema validation."""
    skill_data = {
        "name": "mm_skill_verified",
        "description": "From recording",
        "namespace": "misc",
        "trigger_patterns": ["录制技能"],
        # SkillParameter objects (not plain dicts): the response skill_yaml
        # serialization must normalize them, not crash json.dumps.
        "parameters": [SkillParameter(name="command", required=False)],
        "instructions": "do it",
    }
    fake_synth = MagicMock()
    fake_synth.synthesize = AsyncMock(
        return_value={
            "skill": skill_data,
            "macro_script": _DUMP_YAML,
            "metadata": {"frames_analyzed": 1, "events_processed": 1},
        }
    )
    fake_synth.verify_macro = AsyncMock()

    with (
        patch("app.api.routes.learning.synthesis.os.path.exists", return_value=True),
        patch(
            "app.api.routes.learning.synthesis.MultimodalSkillSynthesizer",
            MagicMock(return_value=fake_synth),
        ),
        patch(
            "app.api.routes.learning.synthesis.publish_skill_mutated",
            new_callable=AsyncMock,
        ),
    ):
        resp = await synthesis_routes.synthesize_from_recording(
            SynthesizeFromRecordingRequest(
                video_path="/tmp/video.mp4",
                session_id="s-verify",
                task_description="recorded task",
            ),
            current_user=SimpleNamespace(id=7),
        )

    assert resp.success is True
    fake_synth.verify_macro.assert_not_called()
    assert resp.verification["status"] == "structure_valid"
    assert resp.verification["step_count"] >= 1
    assert '"name": "command"' in resp.skill_yaml
    row = await _get_skill(resp.skill_id)
    assert row.validation_report["status"] == "structure_valid"
    assert row.macro_id is not None
    macro = await _get_macro(row.macro_id)
    assert macro is not None
    assert macro.macro_script == _DUMP_YAML


def test_reconcile_publishes_after_commit(_real_db):
    """F2 regression: self-heal must publish AFTER the macro patch commits —
    subscribers re-query the row (file export + route index) and previously
    saw the pre-patch macro. Sync test: the test-env task wrapper runs the
    task body via asyncio.run, which conflicts with a running loop."""
    from app.infrastructure.database.sql.database import sync_session_scope

    with sync_session_scope() as session:
        skill = LearnedSkill(
            name="heal_me",
            description="",
            trigger_patterns=json.dumps(["heal_me"]),
            parameters=json.dumps([]),
            status="verified",
            is_active=True,
            member_id=0,
        )
        session.add(skill)
        session.flush()
        sid = skill.id
        macro = Macro(
            name=skill.name,
            description="",
            trigger_patterns=["heal_me"],
            parameters=[],
            macro_script="steps: []",
            status="verified",
            is_active=True,
            fallback_skill_id=sid,
            member_id=0,
        )
        session.add(macro)
        session.flush()
        skill.macro_id = macro.id
        session.flush()
        # The task skips reconciliation with <3 trace events for the thread
        from app.models.learning import TraceEvent

        for i in range(3):
            session.add(
                TraceEvent(
                    thread_id="t-heal",
                    step_number=i,
                    node_name="agent",
                    event_type="click",
                    payload={},
                )
            )
        session.flush()

    seen = {}

    async def fake_publish(*, skill_id, action):
        with sync_session_scope() as session:
            macro = session.get(Macro, (await _get_skill(skill_id)).macro_id)
            seen["macro_script"] = macro.macro_script
            seen["action"] = action

    fake_result = SynthesisResult(
        skill=SynthesizedSkill(name="heal_me", description="", instructions=None),
    )

    fake_compiler = MagicMock()
    fake_compiler.compile.return_value.to_yaml.return_value = "steps:\n  - step_number: 1\n"

    with (
        patch(
            "app.core.learning.workflow_synthesizer.WorkflowSynthesizer",
            MagicMock(
                return_value=MagicMock(synthesize=AsyncMock(return_value=fake_result))
            ),
        ),
        patch(
            "app.core.learning.trace_parser.TraceParser",
            MagicMock(return_value=MagicMock(parse=AsyncMock(return_value=TraceSequence(thread_id="t-heal", steps=[])))),
        ),
        patch(
            "app.core.execution.macro.compiler.MacroScriptCompiler",
            MagicMock(return_value=fake_compiler),
        ),
        patch(
            "app.core.events.publishers.publish_skill_mutated",
            new_callable=AsyncMock,
            side_effect=fake_publish,
        ),
    ):
        from app.core.engine.tasks import reconcile_skill_macro_task

        reconcile_skill_macro_task(skill_id=sid, thread_id="t-heal", model=None)

    assert seen["action"] == "update"
    # The subscriber-visible macro must already hold the patched script
    assert seen["macro_script"] == "steps:\n  - step_number: 1\n"
    with sync_session_scope() as session:
        skill = session.get(LearnedSkill, sid)
        macro = session.get(Macro, skill.macro_id)
        assert macro.macro_script == "steps:\n  - step_number: 1\n"


@pytest.mark.asyncio
async def test_importer_skips_pending_review_rows(_real_db, tmp_path):
    """Echo-guard regression: a file-watcher re-import of a SKILL.md must not
    touch a pending_review row at all (status, activation, instructions, and
    the verification report are owned by the synthesis route until the user
    confirms)."""
    from app.core.learning.skill_importer import SkillImporter

    sid = await _insert_skill(
        name="echo_guard_skill",
        status="pending_review",
        is_active=False,
        instructions="route-owned instructions",
        validation_report={"status": "failed", "error_message": "device gone"},
    )

    skill_dir = tmp_path / "echo_guard_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: echo_guard_skill\n"
        "description: watcher echo\n"
        "namespace: misc\n"
        "trigger_patterns: []\n"
        "parameters: []\n"
        "---\n\n"
        "echo instructions\n"
    )

    result = await SkillImporter.import_single_skill(skill_dir, namespace="misc")
    assert result is True

    row = await _get_skill(sid)
    assert row.status == "pending_review"
    assert row.is_active is False
    assert row.instructions == "route-owned instructions"
    assert row.validation_report == {"status": "failed", "error_message": "device gone"}
