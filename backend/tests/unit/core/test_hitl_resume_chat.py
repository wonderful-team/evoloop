"""HITL resume project_id 透传测试。

覆盖两个缺口：
1. ``_hang_for_resume`` 把 gate 事件里的 ``project_id`` 传递到
   ``BackgroundAgentInputs``（否则 resume 落库丢失项目归属）。
2. ``resume_chat`` 会话模式分支带 project_id 调 ``inject_resume``
   （从 pending 取，缺失时回退 req.project_id）。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.routes.agent.chat import resume_chat
from app.api.schemas.agent import ResumeRequest
from app.core.engine.session.gate import GateEvent
from app.core.engine.session.session import AgentSession, _hang_for_resume


def _req(**overrides):
    base = {
        "thread_id": "t-1",
        "user_input": "某个外部第三方电商平台",
        "model": "m",
        "project_id": 120,
    }
    base.update(overrides)
    return ResumeRequest(**base)


class TestHangForResumeProjectId:
    @pytest.mark.asyncio
    async def test_carries_project_id_into_pending_resume(self):
        """gate 事件里的 project_id 必须进入 BackgroundAgentInputs。"""
        session = AgentSession("t-1")
        session.gate = MagicMock()
        session.gate.wait_next = AsyncMock(
            return_value=GateEvent(
                kind="user_message",
                payload={
                    "hitl_resume_response": "某个外部第三方电商平台",
                    "is_hitl_cancel": False,
                    "resume_kind": "hitl_response",
                    "project_id": 120,
                },
            )
        )
        with patch("app.core.engine.session.session._current_model", return_value="m"):
            await _hang_for_resume(session)

        assert session.pending_resume is not None
        assert session.pending_resume.hitl_resume_response == "某个外部第三方电商平台"
        assert session.pending_resume.project_id == 120
        assert session.pending_resume.metadata == {
            "_resume_kind": "hitl_response",
            "_grant_mode": None,
        }

    @pytest.mark.asyncio
    async def test_second_branch_preserves_input_project_id(self):
        """awaiting_human 期间收到普通 chat 消息 → 从 new_inputs.project_id 保留。"""
        session = AgentSession("t-1")
        session.gate = MagicMock()
        session.gate.wait_next = AsyncMock(
            return_value=GateEvent(
                kind="user_message",
                payload={
                    "inputs": {
                        "goal": "我选外部平台",
                        "model": "m",
                        "project_id": 120,
                    }
                },
            )
        )
        with patch("app.core.engine.session.session._current_model", return_value="m"):
            await _hang_for_resume(session)

        assert session.pending_resume is not None
        assert session.pending_resume.hitl_resume_response == "我选外部平台"
        assert session.pending_resume.project_id == 120


class TestResumeChatSessionMode:
    @pytest.mark.asyncio
    @patch("app.core.engine.session.manager.session_manager")
    @patch(
        "app.core.hitl.orchestrator.HITLOrchestrator.get_pending_request",
        new_callable=AsyncMock,
    )
    async def test_passes_project_id_from_pending(self, mock_get, mock_sm):
        """会话 resume：project_id 从 pending 透传。"""
        mock_get.return_value = {
            "id": "call-1",
            "name": "ask_human",
            "project_id": 120,
        }
        session = MagicMock()
        session.lifecycle = "running"
        mock_sm.get.return_value = session

        resp = await resume_chat(
            _req(), bg_tasks=MagicMock(), _current_user=None, token=None
        )

        assert resp.status == "resuming"
        session.inject_resume.assert_called_once_with(
            "某个外部第三方电商平台", project_id=120, grant_mode=None
        )

    @pytest.mark.asyncio
    @patch("app.core.engine.session.manager.session_manager")
    @patch(
        "app.core.hitl.orchestrator.HITLOrchestrator.get_pending_request",
        new_callable=AsyncMock,
    )
    async def test_falls_back_to_request_project_id(self, mock_get, mock_sm):
        """pending 缺 project_id 时回退 req.project_id。"""
        mock_get.return_value = {"id": "call-1", "name": "ask_human"}
        session = MagicMock()
        session.lifecycle = "running"
        mock_sm.get.return_value = session

        resp = await resume_chat(
            _req(), bg_tasks=MagicMock(), _current_user=None, token=None
        )

        assert resp.status == "resuming"
        session.inject_resume.assert_called_once_with(
            "某个外部第三方电商平台", project_id=120, grant_mode=None
        )


class TestResumeChatSingleShotRawPersist:
    @pytest.mark.asyncio
    @patch("app.core.engine.session.manager.session_manager")
    @patch("app.core.hitl.orchestrator.HITLOrchestrator.get_pending_request")
    @patch("app.core.hitl.orchestrator.HITLOrchestrator.handle_resume")
    @patch("app.core.hitl.orchestrator.HITLOrchestrator.resolve_approved_tool_result")
    @patch("app.core.hitl.orchestrator.HITLOrchestrator.persist_hitl_user_message")
    @patch("app.core.engine.message.repository.MessageRepository")
    async def test_single_shot_persists_raw_user_input(
        self, mock_repo_cls, mock_persist, mock_resolve, mock_resume, mock_get, mock_sm
    ):
        """单发 resume：human 消息按"点了什么存什么"存原始输入（本地化按钮文案
        "拒绝"），而非归一化后的 REJECTED 令牌。"""
        mock_sm.get.return_value = None
        mock_get.return_value = {
            "id": "call-1",
            "name": "ask_confirm",
            "args": {"action_description": "删除文件"},
            "request_id": "req-1",
        }
        mock_resume.return_value = ("REJECTED", True)
        mock_resolve.return_value = "操作已被用户拒绝，未执行"
        repo = AsyncMock()
        repo.get_full_history = AsyncMock(return_value=([], 0, 0))
        mock_repo_cls.return_value = repo

        bg = MagicMock()
        resp = await resume_chat(
            _req(user_input="拒绝"), bg_tasks=bg, _current_user=None, token=None
        )

        assert resp.status == "resuming"
        mock_persist.assert_awaited_once()
        kwargs = mock_persist.await_args.kwargs
        assert kwargs["user_content"] == "拒绝"
        assert kwargs["final_result"] == "操作已被用户拒绝，未执行"
        assert kwargs["tool_call_id"] == "call-1"
        # EMBEDDED_MODE → 经 bg_tasks.add_task 恢复图执行
        assert bg.add_task.called

    @pytest.mark.asyncio
    @patch("app.core.engine.session.manager.session_manager")
    @patch("app.core.hitl.orchestrator.HITLOrchestrator.get_pending_request")
    @patch("app.core.hitl.orchestrator.HITLOrchestrator.handle_resume")
    @patch("app.core.hitl.orchestrator.HITLOrchestrator.resolve_approved_tool_result")
    @patch("app.core.hitl.orchestrator.HITLOrchestrator.persist_hitl_user_message")
    async def test_single_shot_lost_race_skips_reexecution_and_background(
        self, mock_persist, mock_resolve, mock_resume, mock_get, mock_sm
    ):
        """并发 resume 竞态：claimed=False → 不重执行、不再调度 agent 恢复
        （另一端负责），防止同一工具副作用×2。"""
        mock_sm.get.return_value = None
        mock_get.return_value = {
            "id": "call-1",
            "name": "bash",
            "args": {"command": "ls /outside"},
            "request_id": "req-1",
        }
        mock_resume.return_value = ("APPROVED", False)
        bg = MagicMock()
        resp = await resume_chat(
            _req(user_input="yes"), bg_tasks=bg, _current_user=None, token=None
        )

        assert resp.status == "resuming"
        mock_resolve.assert_not_awaited()
        mock_persist.assert_not_awaited()
        assert not bg.add_task.called
