"""Tests for the HITL cancel endpoint (`/hitl/cancel`).

Covers:
1. Live-session mode: cancelling injects a resume event into the session
   (no separate ``resume_agent_background`` re-execution — avoids double run).
2. Single-shot (no live session) mode: falls back to ``handle_cancel`` +
   ``resume_agent_background``.
3. No pending tool: activity state is cleared, returns early.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.routes.agent.hitl import cancel_hitl_request
from app.api.schemas.agent import CancelHITLRequest


def _req(**overrides) -> CancelHITLRequest:
    base = {
        "thread_id": "t-1",
        "model": "model-x",
        "reason": None,
        "project_id": 120,
        "member_id": 0,
    }
    base.update(overrides)
    return CancelHITLRequest(**base)


class TestSessionMode:
    @pytest.mark.asyncio
    @patch("app.core.engine.session.manager.session_manager")
    @patch("app.core.hitl.orchestrator.HITLOrchestrator.get_pending_request")
    async def test_live_session_injects_cancel_no_graph_resume(
        self, mock_get, mock_sm
    ):
        """活 session → inject_resume('CANCELLED')，不触发 resume_agent_background。"""
        mock_get.return_value = {
            "id": "call-1",
            "name": "read_file",
            "args": {"path": "/tmp/x"},
            "request_id": "req-1",
        }
        session = MagicMock()
        session.lifecycle = "running"
        mock_sm.get.return_value = session

        with patch(
            "app.core.engine.resume_runner.resume_agent_background"
        ) as mock_resume:
            resp = await cancel_hitl_request(
                _req(), bg_tasks=MagicMock()
            )

        assert resp.status == "cancelled"
        assert resp.request_id == "call-1"
        session.inject_resume.assert_called_once_with(
            "CANCELLED", is_cancel=True
        )
        mock_resume.assert_not_called()
        # session 模式不直接调 handle_cancel（由 session resume 链路统一处理）
        mock_sm.get.assert_called_once_with("t-1")

    @pytest.mark.asyncio
    @patch("app.core.engine.session.manager.session_manager")
    @patch("app.core.hitl.orchestrator.HITLOrchestrator.get_pending_request")
    async def test_live_session_without_pending_clears_activity(
        self, mock_get, mock_sm
    ):
        """活 session 但无 pending → 仅清理 activity 并注入取消。"""
        mock_get.return_value = None
        session = MagicMock()
        session.lifecycle = "running"
        mock_sm.get.return_value = session

        with patch(
            "app.core.monitoring.activity.activity_monitor.clear_human_request"
        ) as mock_clear:
            resp = await cancel_hitl_request(
                _req(), bg_tasks=MagicMock()
            )

        assert resp.status == "cancelled"
        assert resp.request_id is None
        mock_clear.assert_awaited_once_with("t-1")
        session.inject_resume.assert_called_once_with(
            "CANCELLED", is_cancel=True
        )


class TestSingleShotMode:
    @pytest.mark.asyncio
    @patch("app.core.engine.session.manager.session_manager")
    @patch("app.core.hitl.orchestrator.HITLOrchestrator.get_pending_request")
    async def test_no_session_falls_back_to_graph_resume(
        self, mock_get, mock_sm
    ):
        """无活 session → handle_cancel + resume_agent_background（单发路径）。"""
        mock_get.return_value = {
            "id": "call-1",
            "name": "read_file",
            "args": {"path": "/tmp/x"},
            "request_id": "req-1",
        }
        mock_sm.get.return_value = None

        with patch(
            "app.core.hitl.orchestrator.HITLOrchestrator.handle_cancel",
            new=AsyncMock(return_value="CANCELLED"),
        ) as mock_cancel:
            bg = MagicMock()
            resp = await cancel_hitl_request(_req(), bg_tasks=bg)

        assert resp.status == "cancelled"
        mock_cancel.assert_awaited_once()
        # resume_agent_background 经 bg_tasks.add_task 调度（EMBEDDED_MODE）
        assert bg.add_task.called
        scheduled = bg.add_task.call_args[0]
        assert "resume_agent_background" in str(scheduled[0].__name__)

    @pytest.mark.asyncio
    @patch("app.core.engine.session.manager.session_manager")
    @patch("app.core.hitl.orchestrator.HITLOrchestrator.get_pending_request")
    async def test_no_pending_returns_early(self, mock_get, mock_sm):
        """无 session 且无 pending → 清理 activity 后直接返回，不启动 graph。"""
        mock_get.return_value = None
        mock_sm.get.return_value = None

        with patch(
            "app.core.monitoring.activity.activity_monitor.clear_human_request"
        ) as mock_clear, patch(
            "app.core.engine.resume_runner.resume_agent_background"
        ) as mock_resume:
            resp = await cancel_hitl_request(
                _req(), bg_tasks=MagicMock()
            )

        assert resp.status == "cancelled"
        assert resp.request_id is None
        mock_clear.assert_awaited_once_with("t-1")
        mock_resume.assert_not_called()
