"""SequentialWorkflowNode 多技能顺序工作流（mock 引擎，无 LLM/DB）。

验证：空计划直接 FINISH；多步计划按顺序逐步执行、结果累积、最后路由 FINISH。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.core.engine.message.native_classes import AIMessage
from app.core.engine.nodes import sequential_workflow as seq
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState
from app.core.engine.state.config import ExecutionTicket
from app.models.learning import LearnedSkill

pytestmark = pytest.mark.unit


class _FakeEngine:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = outputs
        self.calls: list[str] = []

    async def run_node(self, state, config, system_prompt, tools, **kwargs):
        # 根据 system_prompt 里提到的 step 返回对应输出
        step = system_prompt or ""
        idx = 0
        if "Step 1" in step:
            idx = 0
        elif "Step 2" in step:
            idx = 1
        self.calls.append(system_prompt or "")
        out = self._outputs[min(idx, len(self._outputs) - 1)]
        return SimpleNamespace(messages=[AIMessage(content=out)])


class _FakePromptBuilder:
    def __init__(self, *args, **kwargs):
        self._step = (kwargs.get("ticket") or getattr(args[-1], "topic", ""))

    async def build(self, config: dict) -> str:
        return self._step or ""

    def build_mission_message(self, session_goal=None, previous_output=""):
        return f"mission: {session_goal} | prev: {previous_output[:20]}"


async def _noop_tools() -> list[Any]:
    return []


def _ticket() -> ExecutionTicket:
    return ExecutionTicket(ticket_type="workflow", topic="wf")


def _state(plan: list[Any], step_index: int, results: list[Any]) -> AgentState:
    return AgentState(
        messages=[],
        workflow_plan=plan,
        workflow_step_index=step_index,
        workflow_results=results,
        ticket=_ticket(),
        session_goal="e2e-wf-goal",
        thread_id="t",
        project_id=0,
    )


def _skill(i: int) -> LearnedSkill:
    return LearnedSkill(id=f"skill-{i}", name=f"Skill {i}", status="verified", is_active=True)


async def _noop_update_agent_state(*_a, **_k) -> None:
    return None


@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setattr(seq, "WorkerPromptBuilder", _FakePromptBuilder)
    from app.core.monitoring import activity as activity_mod

    monkeypatch.setattr(
        activity_mod,
        "activity_monitor",
        SimpleNamespace(update_agent_state=_noop_update_agent_state),
    )
    monkeypatch.setattr(
        seq.tool_manager, "get_node_tools", lambda *a, **k: _noop_tools()
    )


class TestSequentialWorkflowNode:
    async def test_empty_plan_finishes(self) -> None:
        node = seq.SequentialWorkflowNode()
        update = await node(_state([], 0, []), {})
        assert update.next_node == RoutingTarget.FINISH

    async def test_all_steps_completed_finishes(self, _env) -> None:
        node = seq.SequentialWorkflowNode()
        update = await node(_state([], 2, []), {})
        assert update.next_node == RoutingTarget.FINISH

    async def test_runs_all_steps_in_order_then_finish(self, _env, monkeypatch) -> None:
        engine = _FakeEngine(["out-1", "out-2"])
        monkeypatch.setattr(seq, "get_default_engine", lambda: engine)
        node = seq.SequentialWorkflowNode()
        plan = [_skill(1), _skill(2)]

        # 第 1 步
        st1 = _state(plan, 0, [])
        u1 = await node(st1, {})
        assert u1.next_node == RoutingTarget.SEQUENTIAL_WORKFLOW
        assert u1.workflow_step_index == 1
        assert len(u1.workflow_results) == 1
        assert u1.workflow_results[0].skill_name == "Skill 1"
        assert u1.workflow_results[0].status == "success"

        # 第 2 步（最后一步）→ FINISH
        st2 = _state(plan, 1, u1.workflow_results)
        u2 = await node(st2, {})
        assert u2.next_node == RoutingTarget.FINISH
        assert u2.workflow_step_index == 2
        assert len(u2.workflow_results) == 2
        assert u2.workflow_results[1].skill_name == "Skill 2"
        assert u2.workflow_results[1].status == "success"
