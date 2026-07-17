"""Tests for MacroSedimentationService."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.execution.macro.sedimentation_service import MacroSedimentationService
from app.infrastructure.database import session_scope
from app.models import AgentActivity, Message, TraceEvent


async def _insert_activity(thread_id: str, outcome: str, eligible: bool) -> None:
    async with session_scope() as db:
        db.add(
            AgentActivity(
                thread_id=thread_id,
                final_outcome=outcome,
                sedimentation_eligible=eligible,
            )
        )


async def _insert_message(thread_id: str, message_id: str) -> None:
    async with session_scope() as db:
        db.add(
            Message(
                id=message_id,
                thread_id=thread_id,
                role="human",
                content="hi",
            )
        )


async def _insert_event(
    thread_id: str,
    step_number: int,
    event_type: str,
    payload: dict[str, Any] | None = None,
    message_id: str | None = None,
) -> None:
    async with session_scope() as db:
        db.add(
            TraceEvent(
                thread_id=thread_id,
                step_number=step_number,
                event_type=event_type,
                payload=payload or {},
                is_human_action=False,
                message_id=message_id,
                node_name="agent",
            )
        )


@pytest.mark.asyncio
async def test_is_eligible_true_for_replayable_event(_real_db: Any) -> None:
    await _insert_event("t1", 1, "click", payload={"selector": "#btn"})

    result = await MacroSedimentationService.is_eligible("t1")
    assert result is True


@pytest.mark.asyncio
async def test_is_eligible_false_for_noise_only(_real_db: Any) -> None:
    await _insert_event("t1", 1, "llm_output", payload={"content": "hi"})
    await _insert_event("t1", 2, "think", payload={"text": "..."})

    result = await MacroSedimentationService.is_eligible("t1")
    assert result is False


@pytest.mark.asyncio
async def test_is_eligible_false_for_deleted_message_event(_real_db: Any) -> None:
    await _insert_message("t1", "msg-1")
    await _insert_event(
        "t1", 1, "click", payload={"selector": "#btn"}, message_id="deleted-msg"
    )

    result = await MacroSedimentationService.is_eligible("t1")
    assert result is False


@pytest.mark.asyncio
async def test_sediment_disabled_by_config(_real_db: Any) -> None:
    await _insert_activity("t1", "COMPLETED", True)
    await _insert_event("t1", 1, "click", payload={"selector": "#btn"})

    with patch(
        "app.core.execution.macro.sedimentation_service.settings.AUTO_MACRO_SEDIMENTATION_ENABLED",
        False,
    ):
        result = await MacroSedimentationService.sediment("t1")

    assert result is None


@pytest.mark.asyncio
async def test_sediment_skips_when_not_eligible(_real_db: Any) -> None:
    await _insert_activity("t1", "INCOMPLETE", True)
    await _insert_event("t1", 1, "click", payload={"selector": "#btn"})

    result = await MacroSedimentationService.sediment("t1")
    assert result is None


@pytest.mark.asyncio
async def test_sediment_creates_pending_macro(_real_db: Any) -> None:
    await _insert_activity("t1", "COMPLETED", True)
    await _insert_event("t1", 1, "click", payload={"selector": "#btn"})

    fake_skill = MagicMock()
    fake_skill.name = "open_wechat"
    fake_skill.description = "Open WeChat"
    fake_skill.trigger_patterns = ["open wechat"]
    fake_skill.parameters = []
    fake_skill.namespace = "messaging"

    fake_synth = MagicMock()
    fake_synth.synthesize = AsyncMock(return_value=MagicMock(macro=fake_skill))

    fake_compiled = MagicMock()
    fake_compiled.steps = [{"type": "click", "payload": {"selector": "#btn"}}]
    fake_compiled.to_yaml.return_value = "steps:\n  - type: click\n"

    fake_compiler = MagicMock(return_value=MagicMock(compile=lambda _seq: fake_compiled))

    with (
        patch(
            "app.core.learning.workflow_synthesizer.WorkflowSynthesizer",
            return_value=fake_synth,
        ),
        patch(
            "app.core.execution.macro.compiler.MacroScriptCompiler",
            fake_compiler,
        ),
        patch(
            "app.core.events.publishers.publish_macro_mutated",
            new_callable=AsyncMock,
        ) as mock_pub,
    ):
        macro = await MacroSedimentationService.sediment("t1", member_id=7)

    assert macro is not None
    assert macro.name == "open_wechat"
    assert macro.status == "pending_review"
    assert macro.is_active is False
    assert macro.project_id is None
    assert macro.member_id == 7
    mock_pub.assert_awaited_once_with(macro.id, action="create")


@pytest.mark.asyncio
async def test_sediment_skips_when_compiled_steps_empty(_real_db: Any) -> None:
    await _insert_activity("t1", "COMPLETED", True)
    await _insert_event("t1", 1, "click", payload={"selector": "#btn"})

    fake_skill = MagicMock()
    fake_skill.name = "empty"
    fake_skill.description = ""
    fake_skill.trigger_patterns = []
    fake_skill.parameters = []
    fake_skill.namespace = "misc"

    fake_synth = MagicMock()
    fake_synth.synthesize = AsyncMock(return_value=MagicMock(macro=fake_skill))

    fake_compiled = MagicMock()
    fake_compiled.steps = []
    fake_compiled.to_yaml.return_value = "steps: []\n"

    fake_compiler = MagicMock(return_value=MagicMock(compile=lambda _seq: fake_compiled))

    with (
        patch(
            "app.core.learning.workflow_synthesizer.WorkflowSynthesizer",
            return_value=fake_synth,
        ),
        patch(
            "app.core.execution.macro.compiler.MacroScriptCompiler",
            fake_compiler,
        ),
    ):
        macro = await MacroSedimentationService.sediment("t1")

    assert macro is None
