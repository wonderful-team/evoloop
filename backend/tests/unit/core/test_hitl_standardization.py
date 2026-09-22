"""Tests for HITL standardization fixes.

Covers:
1. ``normalize_hitl_input`` fail-safe: empty/None input must resolve to
   REJECTED (never silently APPROVE a sensitive operation).
2. ``finalize_request``: atomically updates BOTH the human_requests and
   messages tracks in a single transaction.
3. ``create_request``: rejects invalid request_type (fail-fast enum validation).
4. ``get_pending_hitl_call``: tool_call_id fallback symmetry with the writer
   (``tool_call_id or request_id``), so close always matches the message.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.hitl.core import (
    HumanInputRequest,
    create_request,
    finalize_request,
)
from app.core.hitl.orchestrator import (
    HITLOrchestrator,
    get_pending_hitl_call,
    normalize_hitl_input,
)


def _mock_async_cm(return_value):
    """Build an async context manager mock whose ``__aenter__`` yields
    ``return_value`` (models ``async with session_scope() as session``)."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=return_value)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


class TestNormalizeHitlInput:
    def _call(self, user_input, request_type=None, **tool_overrides):
        tool_call = {"name": "ask_human", **tool_overrides}
        return normalize_hitl_input(tool_call, user_input, request_type=request_type)

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_empty_approval_is_rejected_not_approved(self, empty):
        # fail-safe: no explicit input must never approve a sensitive op
        assert self._call(empty, request_type="approval") == "REJECTED"

    def test_approval_synonyms(self):
        for word in ("yes", "approve", "approved", "confirm", "ok", "y"):
            assert self._call(word, request_type="approval") == "APPROVED"

    def test_rejection_synonyms(self):
        for word in ("no", "reject", "rejected", "cancel", "deny", "n"):
            assert self._call(word, request_type="approval") == "REJECTED"

    def test_chinese_approval_synonyms(self):
        for word in ("同意", "确认", "批准", "允许", "可以", "好的", "好", "是", "行"):
            assert self._call(word, request_type="approval") == "APPROVED"

    def test_chinese_rejection_synonyms(self):
        for word in ("拒绝", "不同意", "取消", "不行", "否"):
            assert self._call(word, request_type="approval") == "REJECTED"

    def test_ui_button_labels_normalize(self):
        """前端按钮点击后发送的是本地化按钮文案（见 HumanRequestCard），
        必须能归一化为 APPROVED/REJECTED（否则审批判定失效）。"""
        # 中文界面按钮文案
        for word in ("批准", "拒绝"):
            if word == "批准":
                assert self._call(word, request_type="approval") == "APPROVED"
            else:
                assert self._call(word, request_type="approval") == "REJECTED"
        # 确认（confirmation）按钮文案：是 / 否
        assert self._call("是", request_type="confirmation") == "APPROVED"
        assert self._call("否", request_type="confirmation") == "REJECTED"
        # 英文界面按钮文案（首字母大写，normalize 会 lowercase）
        assert self._call("Approve", request_type="approval") == "APPROVED"
        assert self._call("Reject", request_type="approval") == "REJECTED"
        assert self._call("Yes", request_type="confirmation") == "APPROVED"
        assert self._call("No", request_type="confirmation") == "REJECTED"

    def test_unknown_request_type_falls_back_to_heuristic(self):
        """未知 request_type：按 authorization 标记/工具名启发式判定，而非一律透传。"""
        tool_call = {
            "name": "read_file",
            "authorization": {"resource_path": "/x", "action": "read"},
        }
        assert (
            normalize_hitl_input(tool_call, "同意", request_type="bogus") == "APPROVED"
        )
        assert normalize_hitl_input(tool_call, "", request_type="bogus") == "REJECTED"
        assert normalize_hitl_input(tool_call, "yes", request_type=None) == "APPROVED"

    def test_unknown_request_type_without_auth_passthrough(self):
        """未知 request_type 且无 authorization、非确认工具 → 原样返回。"""
        assert (
            normalize_hitl_input({"name": "ask_human"}, "同意", request_type="bogus")
            == "同意"
        )

    def test_free_text_type_preserves_chinese_approval_words(self):
        """自由文本类型下中文同义词是合法内容，不得转成 APPROVED/REJECTED。"""
        assert self._call("同意", request_type="text") == "同意"
        assert self._call("取消", request_type="text") == "取消"
        assert self._call("拒绝", request_type="choice") == "拒绝"

    def test_free_text_passthrough(self):
        assert self._call("hello world", request_type="text") == "hello world"

    def test_text_type_preserves_yes_no(self):
        """ask_human(text) 的 "yes"/"no" 是合法文本，不得转成 APPROVED/REJECTED。"""
        assert self._call("yes", request_type="text") == "yes"
        assert self._call("no", request_type="text") == "no"
        assert self._call("cancel", request_type="text") == "cancel"

    def test_choice_type_preserves_input(self):
        assert self._call("选项B", request_type="choice") == "选项B"

    def test_authorization_gate_normalizes_without_request_type(self):
        """授权门控（无 request_type 时按 authorization 标记判定）→ 归一化。"""
        tool_call = {
            "name": "read_file",
            "authorization": {"resource_path": "/x", "action": "read"},
        }
        assert normalize_hitl_input(tool_call, "yes") == "APPROVED"
        assert normalize_hitl_input(tool_call, "") == "REJECTED"

    def test_unknown_type_falls_back_to_tool_name(self):
        """无 request_type 且无 authorization：ask_confirm 仍归一化。"""
        assert normalize_hitl_input({"name": "ask_confirm"}, "yes") == "APPROVED"


class TestCreateRequestValidation:
    @pytest.mark.asyncio
    @patch("app.core.hitl.core.session_scope")
    async def test_invalid_type_fails_fast(self, mock_scope):
        """Invalid request_type must raise, not silently persist."""
        with pytest.raises(ValueError):
            await create_request(
                thread_id="t-1",
                request_type="bogus_type",
                prompt="p",
            )
        mock_scope.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.core.hitl.core.gen_uuid", return_value="req-1")
    @patch("app.core.hitl.core.session_scope")
    async def test_valid_type_persists(self, mock_scope, mock_uuid):
        from datetime import datetime

        session = MagicMock()
        mock_scope.return_value = _mock_async_cm(session)

        captured = {}

        def _capture_add(obj):
            captured["db"] = obj

        session.add.side_effect = _capture_add

        async def _flush():
            # simulate ORM default: created_at populated on flush
            captured["db"].created_at = datetime.utcnow()

        session.flush = AsyncMock(side_effect=_flush)

        result = await create_request(
            thread_id="t-1",
            request_type="approval",
            prompt="approve?",
        )
        assert isinstance(result, HumanInputRequest)
        assert result.request_type == "approval"


class TestFinalizeRequest:
    @pytest.mark.asyncio
    @patch("app.core.hitl.core.session_scope")
    async def test_updates_both_tracks_atomically(self, mock_scope):
        session = MagicMock()
        mock_scope.return_value = _mock_async_cm(session)

        exec_side_effects = [
            type("R", (), {"rowcount": 1})(),  # human_requests update
            type("R", (), {"rowcount": 1})(),  # messages update
        ]
        session.execute = AsyncMock(side_effect=exec_side_effects)

        ok = await finalize_request(
            thread_id="t-1",
            request_id="req-1",
            tool_call_id="call-1",
            status="completed",
            response="APPROVED",
        )
        assert ok is True
        assert session.execute.await_count == 2

    @pytest.mark.asyncio
    @patch("app.core.hitl.core.session_scope")
    async def test_no_tool_call_id_updates_request_only(self, mock_scope):
        session = MagicMock()
        mock_scope.return_value = _mock_async_cm(session)
        session.execute = AsyncMock(return_value=type("R", (), {"rowcount": 1})())

        ok = await finalize_request(
            thread_id="t-1",
            request_id="req-1",
            tool_call_id=None,
            status="cancelled",
        )
        assert ok is True
        assert session.execute.await_count == 1

    @pytest.mark.asyncio
    @patch("app.core.hitl.core.session_scope")
    async def test_closes_sibling_requests_with_same_key(self, mock_scope):
        """批准时带 sibling_key → 关闭同线程同工具同参数的兄弟 pending 请求。"""
        session = MagicMock()
        mock_scope.return_value = _mock_async_cm(session)

        # 兄弟消息（同工具同参数）：refund_agree + order_goods_id=246
        sibling = type(
            "Msg",
            (),
            {
                "id": "msg-sibling",
                "meta_data": {
                    "original_tool": {
                        "name": "mcp__capability_matrix__refund_agree",
                        "args": {"order_goods_id": 246},
                    },
                    "hitl_request_id": "req-sibling",
                },
            },
        )
        sibling_scalars = type("S", (), {"all": lambda self: [sibling]})()
        query_result = type("Q", (), {"scalars": lambda self: sibling_scalars})()
        # 前两次 update（当前 request/message）+ 1 次查询兄弟 + 1 次关 message + 1 次关 human_request
        session.execute = AsyncMock(
            side_effect=[
                type("R", (), {"rowcount": 1})(),
                type("R", (), {"rowcount": 1})(),
                query_result,
                type("R", (), {"rowcount": 1})(),
                type("R", (), {"rowcount": 1})(),
            ]
        )

        ok = await finalize_request(
            thread_id="t-1",
            request_id="req-1",
            tool_call_id="call-1",
            status="completed",
            response="APPROVED",
            sibling_key={
                "name": "mcp__capability_matrix__refund_agree",
                "args": {"order_goods_id": 246},
            },
        )
        assert ok is True
        # 当前请求(2) + 兄弟查询(1) + 兄弟关闭 message(1) + 兄弟关闭 request(1)
        assert session.execute.await_count == 5

    @pytest.mark.asyncio
    @patch("app.core.hitl.core.session_scope")
    async def test_skips_sibling_close_without_key(self, mock_scope):
        """不传 sibling_key → 只关闭当前请求，无额外查询。"""
        session = MagicMock()
        mock_scope.return_value = _mock_async_cm(session)
        session.execute = AsyncMock(return_value=type("R", (), {"rowcount": 1})())

        ok = await finalize_request(
            thread_id="t-1",
            request_id="req-1",
            tool_call_id="call-1",
            status="completed",
            response="APPROVED",
        )
        assert ok is True
        assert session.execute.await_count == 2

    @pytest.mark.asyncio
    @patch("app.core.hitl.core.session_scope")
    async def test_sibling_close_ignores_different_key(self, mock_scope):
        """兄弟请求参数不同 → 不关闭，仅关闭当前请求。"""
        session = MagicMock()
        mock_scope.return_value = _mock_async_cm(session)

        sibling = type(
            "Msg",
            (),
            {
                "id": "msg-sibling",
                "meta_data": {
                    "original_tool": {
                        "name": "mcp__capability_matrix__refund_agree",
                        "args": {"order_goods_id": 999},  # 不同参数
                    },
                    "hitl_request_id": "req-sibling",
                },
            },
        )
        sibling_scalars = type("S", (), {"all": lambda self: [sibling]})()
        query_result = type("Q", (), {"scalars": lambda self: sibling_scalars})()
        session.execute = AsyncMock(
            side_effect=[
                type("R", (), {"rowcount": 1})(),
                type("R", (), {"rowcount": 1})(),
                query_result,
            ]
        )

        ok = await finalize_request(
            thread_id="t-1",
            request_id="req-1",
            tool_call_id="call-1",
            status="completed",
            response="APPROVED",
            sibling_key={
                "name": "mcp__capability_matrix__refund_agree",
                "args": {"order_goods_id": 246},
            },
        )
        assert ok is True
        # 只多了一次查询，兄弟参数不同不关闭
        assert session.execute.await_count == 3


class TestPendingHitlCallSymmetry:
    @pytest.mark.asyncio
    @patch("app.core.hitl.orchestrator.session_scope")
    async def test_tool_call_id_falls_back_to_request_id(self, mock_scope):
        """Writer stores tool_call_id or request_id; reader must use the SAME
        fallback so message closure (finalize) matches the message."""
        session = MagicMock()
        mock_scope.return_value = _mock_async_cm(session)

        last = type(
            "Msg",
            (),
            {
                "tool_call_id": None,  # no tool call id → writer stored request_id
                "id": "message-uuid-1",
                "tool_name": "read_file",
                "project_id": 120,
                "content": json.dumps(
                    {"id": "req-abc", "type": "approval", "prompt": "approve?"}
                ),
                "meta_data": {
                    "original_tool": {"name": "read_file", "args": {"path": "/x"}},
                    "hitl_request_id": "req-abc",
                    "authorization": {"resource_path": "/x", "action": "read"},
                },
            },
        )
        scalars = type("S", (), {"first": lambda self: last})()
        result = type("R", (), {"scalars": lambda self: scalars})()
        session.execute = AsyncMock(return_value=result)

        pending = await get_pending_hitl_call({"configurable": {"thread_id": "t-1"}})
        # CRITICAL: must fall back to request_id (not message.id), symmetric
        # with the writer's `tool_call_id or request_id` in push_hitl_notification.
        assert pending["id"] == "req-abc"
        # request_type 从 message content 解析（供 normalize 判定是否归一化）
        assert pending["request_type"] == "approval"
        # project_id 随 pending 透传，供 resume 落库（避免丢失项目归属）
        assert pending["project_id"] == 120

    @pytest.mark.asyncio
    @patch("app.core.hitl.orchestrator.session_scope")
    async def test_request_type_parsed_from_text_message(self, mock_scope):
        """text 类型消息 → request_type='text'，resume 端据此保留原始文本。"""
        session = MagicMock()
        mock_scope.return_value = _mock_async_cm(session)

        last = type(
            "Msg",
            (),
            {
                "tool_call_id": "call-text-1",
                "id": "message-uuid-2",
                "tool_name": "ask_human",
                "project_id": 120,
                "content": json.dumps({"id": "req-2", "type": "text", "prompt": "?"}),
                "meta_data": {
                    "original_tool": {"name": "ask_human", "args": {}},
                    "hitl_request_id": "req-2",
                },
            },
        )
        scalars = type("S", (), {"first": lambda self: last})()
        result = type("R", (), {"scalars": lambda self: scalars})()
        session.execute = AsyncMock(return_value=result)

        pending = await get_pending_hitl_call({"configurable": {"thread_id": "t-1"}})
        assert pending["request_type"] == "text"
        assert pending["authorization"] is None
        assert pending["project_id"] == 120


class TestResumeAndPersist:
    @pytest.mark.asyncio
    @patch("app.core.hitl.orchestrator.get_runtime")
    async def test_consumes_pending_and_persists(self, mock_get_runtime):
        pending = {
            "id": "call-1",
            "name": "list_dir",
            "args": {"path": "/tmp/x"},
            "authorization": {"resource_path": "/tmp/x", "action": "read"},
        }
        runtime = mock_get_runtime.return_value
        runtime.persist_hitl_user_message = AsyncMock()
        with (
            patch.object(
                HITLOrchestrator,
                "get_pending_request",
                new=AsyncMock(return_value=pending),
            ) as mock_get,
            patch.object(
                HITLOrchestrator,
                "handle_resume",
                new=AsyncMock(return_value=("APPROVED", True)),
            ) as mock_resume,
            patch.object(
                HITLOrchestrator,
                "resolve_approved_tool_result",
                new=AsyncMock(return_value="✅ done"),
            ) as mock_resolve,
        ):
            ok = await HITLOrchestrator.resume_and_persist(
                thread_id="t-1",
                project_id=120,
                member_id=0,
                config={
                    "configurable": {"thread_id": "t-1", "model": "m"},
                    "metadata": {"project_id": 120},
                },
                user_input="yes",
                state=None,
            )
        assert ok is True
        mock_get.assert_awaited_once()
        mock_resume.assert_awaited_once()
        mock_resolve.assert_awaited_once()
        # 编排层把"用户答复 + 原始工具结果"原样委托给 engine runtime：
        # human 落库语义（role/content/category）由 HitlEngineRuntime 单测与
        # 集成测试覆盖。
        runtime.persist_hitl_user_message.assert_awaited_once_with(
            thread_id="t-1",
            project_id=120,
            member_id=0,
            tool_call_id="call-1",
            user_content="yes",
            final_result="✅ done",
        )

    @pytest.mark.asyncio
    @patch("app.core.hitl.orchestrator.get_runtime")
    async def test_lost_race_skips_reexecution(self, mock_get_runtime):
        """并发 resume 竞态：claimed=False（pending 已被其他端消费）→
        不得重执行工具、不得再触发 agent 恢复（副作用×2 防护）。"""
        pending = {
            "id": "call-1",
            "name": "bash",
            "args": {"command": "ls /outside"},
            "authorization": {"resource_path": "/outside", "action": "read"},
        }
        runtime = mock_get_runtime.return_value
        runtime.persist_hitl_user_message = AsyncMock()
        with (
            patch.object(
                HITLOrchestrator,
                "get_pending_request",
                new=AsyncMock(return_value=pending),
            ),
            patch.object(
                HITLOrchestrator,
                "handle_resume",
                new=AsyncMock(return_value=("APPROVED", False)),
            ),
            patch.object(
                HITLOrchestrator,
                "resolve_approved_tool_result",
                new=AsyncMock(return_value="should not run"),
            ) as mock_resolve,
        ):
            ok = await HITLOrchestrator.resume_and_persist(
                thread_id="t-1",
                project_id=120,
                member_id=0,
                config={"configurable": {"thread_id": "t-1", "model": "m"}},
                user_input="yes",
                state=None,
            )
        assert ok is False
        mock_resolve.assert_not_awaited()
        runtime.persist_hitl_user_message.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("app.core.hitl.orchestrator.get_runtime")
    async def test_no_pending_returns_false(self, mock_get_runtime):
        runtime = mock_get_runtime.return_value
        runtime.persist_hitl_user_message = AsyncMock()
        with patch.object(
            HITLOrchestrator, "get_pending_request", new=AsyncMock(return_value=None)
        ):
            ok = await HITLOrchestrator.resume_and_persist(
                thread_id="t-1",
                project_id=120,
                member_id=0,
                config={"configurable": {"thread_id": "t-1", "model": "m"}},
                user_input="yes",
            )
        assert ok is False
        runtime.persist_hitl_user_message.assert_not_awaited()


class TestRaiseApproval:
    """统一 approval 发起（create + push + raise）helper 的语义。"""

    @pytest.mark.asyncio
    @patch("app.core.hitl.core.push_hitl_notification")
    @patch("app.core.hitl.core.create_request")
    async def test_creates_push_raises(self, mock_create, mock_push):
        """create_request → push_hitl_notification → raise_hitl_interrupt 三步。"""
        from app.core.exceptions import AgentHumanInterruptException
        from app.core.hitl.core import HumanInputRequest

        mock_create.return_value = HumanInputRequest(
            id="req-1", thread_id="t-1", request_type="approval", prompt="删除文件"
        )

        with pytest.raises(AgentHumanInterruptException) as excinfo:
            await HITLOrchestrator.raise_approval(
                thread_id="t-1",
                prompt="删除文件",
                context="风险等级：高",
                tool_name="ask_confirm",
                risk_level="high",
                project_id=120,
            )

        mock_create.assert_awaited_once()
        mock_push.assert_awaited_once()
        # raise 的中断文本包含请求 ID
        assert "req-1" in str(excinfo.value)

    @pytest.mark.asyncio
    @patch("app.core.hitl.orchestrator.raise_hitl_interrupt")
    @patch("app.core.hitl.core.push_hitl_notification")
    @patch("app.core.hitl.core.create_request")
    async def test_passes_authorization_metadata(
        self, mock_create, mock_push, mock_raise
    ):
        """skip_grant / original_tool / resource_path 正确透传给 push。"""
        from app.core.hitl.core import HumanInputRequest

        mock_create.return_value = HumanInputRequest(
            id="req-1", thread_id="t-1", request_type="approval", prompt="执行宏"
        )

        await HITLOrchestrator.raise_approval(
            thread_id="t-1",
            prompt="执行宏",
            context="宏确认",
            tool_name="run_macro",
            risk_level="high",
            project_id=120,
            original_tool_name="run_macro",
            original_tool_args={"macro_id": 1},
            skip_grant=True,
            action="macro_run",
            resource_path="macro:1",
        )

        mock_push.assert_awaited_once()
        kwargs = mock_push.await_args.kwargs
        assert kwargs["skip_grant"] is True
        assert kwargs["original_tool_name"] == "run_macro"
        assert kwargs["original_tool_args"] == {"macro_id": 1}
        assert kwargs["action"] == "macro_run"
        assert kwargs["resource_path"] == "macro:1"

    @pytest.mark.asyncio
    @patch("app.core.hitl.orchestrator.raise_hitl_interrupt")
    @patch("app.core.hitl.core.push_hitl_notification")
    @patch("app.core.hitl.core.create_request")
    async def test_response_factory_customizes_text(
        self, mock_create, mock_push, mock_raise
    ):
        """response_text_factory 可自定义中断文本（如 ask_confirm 的 i18n 模板）。"""
        from app.core.hitl.core import HumanInputRequest

        mock_create.return_value = HumanInputRequest(
            id="req-1", thread_id="t-1", request_type="approval", prompt="操作"
        )

        await HITLOrchestrator.raise_approval(
            thread_id="t-1",
            prompt="操作",
            context="上下文",
            tool_name="ask_confirm",
            risk_level="medium",
            response_text_factory=lambda req: f"自定义文本 {req.id}",
        )

        mock_raise.assert_called_once()
        assert mock_raise.call_args.args[1] == "自定义文本 req-1"
