"""FinishNode 审计收口单测（mock 审计服务，无 LLM/DB）。

覆盖 finish.py 两个关键门控：
  1. 审计判 INCOMPLETE 且未到迭代上限 → 重路由回 Supervisor。
  2. STOP hook 阻断完成（quality gate 拦截）→ 回 Supervisor 并标记 blocked_by_hook。
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.engine.nodes import finish as finish_mod
from app.core.engine.routers import RoutingTarget
from app.core.engine.services.audit_service import AuditResult
from app.core.engine.state import AgentState

pytestmark = pytest.mark.unit


class _FakeAudit:
    def __init__(self, outcome: str) -> None:
        self.outcome = outcome

    async def execute(self, **kwargs: Any) -> AuditResult:
        return AuditResult(
            summary=f"audit {self.outcome}", meta={"outcome": self.outcome}
        )


def _state() -> AgentState:
    return AgentState(
        messages=[],
        iteration_count=0,
        tool_history=[],
        thread_id="t-finish",
        project_id=0,
        session_goal="e2e-finish-goal",
    )


async def _noop(*_a, **_k) -> None:
    return None


def _patch_node_db_deps(node: finish_mod.FinishNode) -> None:
    """DB 依赖方法 mock 为 no-op。"""
    node._update_agent_activity = _noop
    node._has_replayable_steps = _noop_false


async def _noop_false(*_a, **_k) -> bool:
    return False


class TestFinishAuditRouting:
    async def test_incomplete_routes_to_supervisor(self, monkeypatch) -> None:
        node = finish_mod.FinishNode(audit_service=_FakeAudit("INCOMPLETE"))
        _patch_node_db_deps(node)
        update = await node(_state(), {"configurable": {}})
        assert update.next_node == RoutingTarget.SUPERVISOR
        assert update.worker_outcome == "incomplete"
        assert update.final_outcome == "INCOMPLETE"

    async def test_incomplete_at_iteration_limit_forces_completion(
        self, monkeypatch
    ) -> None:
        from app.core.engine.hooks.schemas import HookResult

        node = finish_mod.FinishNode(audit_service=_FakeAudit("INCOMPLETE"))
        _patch_node_db_deps(node)
        from app.core.engine import hooks as hooks_mod

        async def _ok_trigger(*_a, **_k):
            return HookResult(success=True, block=False)

        monkeypatch.setattr(hooks_mod.hook_system, "trigger", _ok_trigger)
        state = _state()
        state.iteration_count = 1
        state.max_supervisor_steps = 1  # iteration_count(1) >= 上限 → 强制完成
        update = await node(state, {"configurable": {}})
        # 迭代上限 → 强制完成，不应回 Supervisor
        assert update.next_node != RoutingTarget.SUPERVISOR

    async def test_stop_hook_block_routes_to_supervisor(self, monkeypatch) -> None:
        from app.core.engine.hooks.schemas import HookResult

        node = finish_mod.FinishNode(audit_service=_FakeAudit("COMPLETED"))
        _patch_node_db_deps(node)
        from app.core.engine import hooks as hooks_mod

        async def _block_trigger(*_a, **_k):
            return HookResult(success=False, block=True, message="quality gate")

        monkeypatch.setattr(hooks_mod.hook_system, "trigger", _block_trigger)
        update = await node(_state(), {"configurable": {}})
        assert update.next_node == RoutingTarget.SUPERVISOR
        assert update.blocked_by_hook is True
        assert update.worker_outcome == "failed"
