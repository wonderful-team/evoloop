"""End-to-end flywheel sedimentation test.

This test runs the real agent execution loop (app.core.engine.loop.run_node_loop)
with a real SQLite database, then verifies that a completed session with
replayable trace events produces a pending_review macro via the
MacroSedimentationSubscriber.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.engine import AgentEngine, set_default_engine
from app.core.engine.loop import run_node_loop
from app.core.engine.message.native_classes import AIMessage, HumanMessage
from app.core.engine.nodes.supervisor import SupervisorNode
from app.core.engine.nodes.worker import WorkerNode
from app.core.engine.routers import RoutingTarget
from app.core.engine.schemas import EngineResult
from app.core.engine.services.audit_service import AuditResult
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.config import ExecutionTicket
from app.core.events.base import system_bus
from app.core.execution.macro.event.subscribers import MacroSedimentationSubscriber
from app.infrastructure.database import session_scope
from app.models import AgentActivity, Macro, TraceEvent


class _MockAgentEngine(AgentEngine):
    """No-op engine: nodes are short-circuited via prepare_state patches."""

    async def run_node(self, *args: Any, **kwargs: Any) -> EngineResult:
        return EngineResult()


async def _seed_activity_and_trace(thread_id: str) -> None:
    async with session_scope() as db:
        db.add(
            AgentActivity(
                thread_id=thread_id,
                status="idle",
                final_outcome="INCOMPLETE",
                sedimentation_eligible=False,
            )
        )

    async with session_scope() as db:
        db.add(
            TraceEvent(
                thread_id=thread_id,
                step_number=1,
                event_type="click",
                payload={"selector": "#submit"},
                node_name="worker",
                is_human_action=False,
                source="agent",
            )
        )


@pytest.mark.asyncio
async def test_flywheel_creates_pending_macro_after_completed_session(
    _real_db: Any,
) -> None:
    thread_id = "flywheel-e2e-test"
    member_id = 7

    await _seed_activity_and_trace(thread_id)

    ctx = EvoContext(
        thread_id=thread_id,
        project_id=1,
        member_id=member_id,
        active_model="kimi-k2-thinking-turbo",
    )
    ContextManager.set(ctx)

    set_default_engine(_MockAgentEngine())

    system_bus.clear()
    MacroSedimentationSubscriber()

    async def _supervisor_prepare(_self: SupervisorNode, _state: AgentState, _config: dict[str, Any]) -> StateUpdate:
        return StateUpdate(next_node=RoutingTarget.WORKER)

    async def _worker_prepare(_self: WorkerNode, _state: AgentState, _config: dict[str, Any]) -> StateUpdate:
        return StateUpdate(
            messages=[AIMessage(content="Clicked the submit button")],
            worker_outcome="success",
            next_node=RoutingTarget.FINISH,
        )

    fake_skill = MagicMock()
    fake_skill.name = "submit_form"
    fake_skill.description = "Submit the form"
    fake_skill.trigger_patterns = ["submit"]
    fake_skill.parameters = []
    fake_skill.namespace = "ui"

    fake_synth = MagicMock()
    fake_synth.synthesize = AsyncMock(return_value=MagicMock(macro=fake_skill))

    fake_compiled = MagicMock()
    fake_compiled.steps = [{"type": "click", "payload": {"selector": "#submit"}}]
    fake_compiled.to_yaml.return_value = (
        "steps:\n"
        "  - type: click\n"
        "    payload:\n"
        "      selector: '#submit'\n"
    )
    fake_compiler = MagicMock(
        return_value=MagicMock(compile=lambda _seq: fake_compiled)
    )

    fake_audit = AuditResult(
        summary="Session completed successfully",
        meta={"outcome": "COMPLETED"},
    )

    config = {
        "configurable": {
            "thread_id": thread_id,
            "run_id": "flywheel-run-1",
            "model": "kimi-k2-thinking-turbo",
        },
        "metadata": {"project_id": 1, "member_id": member_id},
    }

    with (
        patch.object(SupervisorNode, "prepare_state", _supervisor_prepare),
        patch.object(WorkerNode, "prepare_state", _worker_prepare),
        patch("app.core.monitoring.activity.activity_monitor.update_agent_state", new_callable=AsyncMock),
        patch("app.core.monitoring.activity.activity_monitor.check_cancellation", new_callable=AsyncMock, return_value=False),
        patch("app.core.engine.nodes.finish.AuditService") as mock_audit_cls,
        patch(
            "app.core.learning.workflow_synthesizer.WorkflowSynthesizer",
            return_value=fake_synth,
        ),
        patch(
            "app.core.execution.macro.compiler.MacroScriptCompiler",
            fake_compiler,
        ),
    ):
        mock_audit_cls.return_value.execute = AsyncMock(return_value=fake_audit)

        state = AgentState(
            messages=[HumanMessage(content="Click the submit button")],
            next_node=RoutingTarget.SUPERVISOR,
            ticket=ExecutionTicket(topic="ui_action", reason="test", ticket_type="task"),
        )
        await run_node_loop(state, config, thread_id, max_loop_steps=20)

    async with session_scope() as db:
        macro = (
            await db.execute(
                select(Macro).where(Macro.source_thread_id == thread_id)
            )
        ).scalar_one_or_none()

    assert macro is not None
    assert macro.name == "submit_form"
    assert macro.status == "pending_review"
    assert macro.is_active is False
    assert macro.member_id == member_id
    assert macro.project_id is None
    assert macro.source_thread_id == thread_id

    async with session_scope() as db:
        activity = await db.get(AgentActivity, thread_id)
    assert activity is not None
    assert activity.final_outcome == "COMPLETED"
    assert activity.sedimentation_eligible is True
    assert activity.summary == "Session completed successfully"
