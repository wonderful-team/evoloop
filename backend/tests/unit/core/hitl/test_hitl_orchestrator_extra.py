"""Tests for HITLOrchestrator flows not covered elsewhere.

Covers: ``request_authorization`` full chain, ``raise_approval`` response-text
branches, pending detection metadata surfacing, and re-execution resilience
when grant persistence fails.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.hitl.core import HumanInputRequest
from app.core.hitl.orchestrator import (
    HITLOrchestrator,
    close_hitl_message,
    get_pending_hitl_call,
)


def _request() -> HumanInputRequest:
    return HumanInputRequest(
        id="req-1",
        thread_id="t-1",
        request_type="approval",
        prompt="p",
        context="c",
        default_value="REJECTED",
        created_at=datetime.utcnow(),
    )


def _mock_async_cm(return_value):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=return_value)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ============ request_authorization ============


class TestRequestAuthorization:
    @pytest.mark.asyncio
    async def test_request_authorization_writes_all_paths_metadata(self):
        """extra_paths 全量写入 authorization.all_paths（含首路径）——
        resolve 批准/拒绝只认这份单一列表。走真实 push_hitl_notification，
        在 engine runtime 边界断言元数据。"""
        runtime = MagicMock()
        runtime.push_hitl_request = MagicMock()
        mock_sink = patch("app.core.hitl.core.get_activity_sink").start()
        mock_sink.return_value.set_human_request = AsyncMock()
        patch("app.core.hitl.orchestrator.raise_hitl_interrupt", side_effect=RuntimeError("interrupt")).start()
        with (
            patch(
                "app.core.hitl.orchestrator.create_request",
                AsyncMock(return_value=_request()),
            ),
            patch(
                "app.core.hitl.core.get_runtime",
                return_value=runtime,
            ),
        ):
            with pytest.raises(RuntimeError):
                await HITLOrchestrator.request_authorization(
                    thread_id="t-1",
                    action_description="read /a and /b",
                    resource_path="/a",
                    risk_level="high",
                    policy={"description": "d"},
                    project_id=120,
                    tool_call_id="call-1",
                    original_tool_name="bash",
                    original_tool_args={"command": "ls /a; ls /b"},
                    action="read",
                    extra_paths=[("/a", "read"), ("/b", "read")],
                )

        metadata = runtime.push_hitl_request.call_args.kwargs["metadata"]
        auth_meta = metadata["authorization"]
        assert auth_meta["resource_path"] == "/a"
        assert auth_meta["action"] == "read"
        assert [list(x) for x in auth_meta["all_paths"]] == [
            ["/a", "read"],
            ["/b", "read"],
        ]

        # 前端按钮判定标记：payload.resource_path 在场 = 授权门控请求
        request_data = mock_sink.return_value.set_human_request.await_args.kwargs[
            "request_data"
        ]
        assert request_data["payload"]["resource_path"] == "/a"
        assert request_data["payload"]["action"] == "read"

    async def test_full_chain_builds_approval_with_policy_context(self):
        with (
            patch(
                "app.core.hitl.orchestrator.create_request",
                AsyncMock(return_value=_request()),
            ) as mock_create,
            patch(
                "app.core.hitl.orchestrator.push_hitl_notification", AsyncMock()
            ) as mock_push,
            patch(
                "app.core.hitl.orchestrator.raise_hitl_interrupt",
                side_effect=RuntimeError("interrupt"),
            ),
        ):
            with pytest.raises(RuntimeError):
                await HITLOrchestrator.request_authorization(
                    thread_id="t-1",
                    action_description="read keys/.env",
                    resource_path="keys/.env",
                    risk_level="high",
                    policy={"description": "Env files may contain secrets."},
                    project_id=120,
                    run_id="r-1",
                    tool_call_id="call-1",
                    parent_id="m-1",
                    original_tool_name="read_file",
                    original_tool_args={"path": "/proj/keys/.env"},
                )

        mock_create.assert_awaited_once_with(
            thread_id="t-1",
            request_type="approval",
            prompt="read keys/.env",
            context=mock_push.await_args.kwargs["request_data"]["context"],
            default_value="REJECTED",
            resource_path="keys/.env",
            resource_action="read",
        )
        push_kwargs = mock_push.await_args.kwargs
        assert "Env files may contain secrets" in push_kwargs["request_data"]["context"]
        assert push_kwargs["request_data"]["risk_level"] == "high"
        assert push_kwargs["tool_name"] == "request_approval"
        assert push_kwargs["original_tool_name"] == "read_file"
        assert push_kwargs["original_tool_args"] == {"path": "/proj/keys/.env"}
        assert push_kwargs["resource_path"] == "keys/.env"
        assert push_kwargs["action"] == "read"  # action 从 action_description 首词提取


# ============ raise_approval branches ============


class TestRaiseApproval:
    @pytest.mark.asyncio
    async def test_default_response_text(self):
        with (
            patch(
                "app.core.hitl.core.create_request", AsyncMock(return_value=_request())
            ),
            patch("app.core.hitl.core.push_hitl_notification", AsyncMock()),
            patch(
                "app.core.hitl.orchestrator.raise_hitl_interrupt",
                side_effect=RuntimeError("interrupt"),
            ),
        ):
            with pytest.raises(RuntimeError):
                await HITLOrchestrator.raise_approval(
                    thread_id="t-1",
                    prompt="approve?",
                    context="ctx",
                    tool_name="ask_confirm",
                    risk_level="medium",
                )
        from app.core.hitl.orchestrator import i18n

        expected = i18n.get("hitl.approval_default", id="req-1")
        assert "req-1" in expected

    @pytest.mark.asyncio
    async def test_response_template_replaces_id_and_prompt(self):
        with (
            patch(
                "app.core.hitl.core.create_request", AsyncMock(return_value=_request())
            ),
            patch("app.core.hitl.core.push_hitl_notification", AsyncMock()),
            patch(
                "app.core.hitl.orchestrator.raise_hitl_interrupt",
                side_effect=RuntimeError("interrupt"),
            ) as mock_interrupt,
        ):
            with pytest.raises(RuntimeError):
                await HITLOrchestrator.raise_approval(
                    thread_id="t-1",
                    prompt="完成退款{query}",
                    context="ctx",
                    tool_name="run_macro",
                    risk_level="high",
                    response_template="高风险宏（ID: {id}）: {prompt} 待确认",
                )
        # {id}/{prompt} 被替换；{query} 花括号原样保留（不能走 str.format）
        text = mock_interrupt.call_args.args[1]
        assert "req-1" in text
        assert "完成退款{query}" in text
        assert "{id}" not in text and "{prompt}" not in text

    @pytest.mark.asyncio
    async def test_response_text_factory_used(self):
        captured = {}

        def factory(request):
            captured["request"] = request
            return f"自定义文案 {request.id}"

        with (
            patch(
                "app.core.hitl.core.create_request", AsyncMock(return_value=_request())
            ),
            patch("app.core.hitl.core.push_hitl_notification", AsyncMock()),
            patch(
                "app.core.hitl.orchestrator.raise_hitl_interrupt",
                side_effect=RuntimeError("interrupt"),
            ),
        ):
            with pytest.raises(RuntimeError):
                await HITLOrchestrator.raise_approval(
                    thread_id="t-1",
                    prompt="approve?",
                    context="ctx",
                    tool_name="ask_confirm",
                    risk_level="low",
                    response_text_factory=factory,
                )
        assert captured["request"].id == "req-1"


# ============ get_pending_hitl_call metadata surfacing ============


def _hitl_message(**meta_overrides) -> MagicMock:
    msg = MagicMock()
    msg.tool_call_id = None  # 触发 tool_call_id → request_id fallback
    msg.tool_name = "ask_confirm"
    msg.meta_data = {
        "original_tool": {"name": "ask_confirm", "args": {"macro_id": 7}},
        "hitl_request_id": "req-1",
        "authorization": {"resource_path": "x", "action": "write", "skip_grant": True},
        "resume": {"args": {"skip_confirmation": True}},
        **meta_overrides,
    }
    msg.content = '{"type": "approval", "prompt": "p"}'
    return msg


@pytest.mark.asyncio
@patch("app.core.hitl.orchestrator.session_scope")
async def test_get_pending_surfaces_resume_and_authorization(mock_scope):
    session = MagicMock()
    mock_scope.return_value = _mock_async_cm(session)
    scalars = MagicMock()
    scalars.first.return_value = _hitl_message()
    result = MagicMock()
    result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=result)

    pending = await get_pending_hitl_call({"configurable": {"thread_id": "t-1"}})
    assert pending["name"] == "ask_confirm"
    assert pending["request_type"] == "approval"
    assert pending["authorization"] == {
        "resource_path": "x",
        "action": "write",
        "skip_grant": True,
    }
    assert pending["resume"] == {"args": {"skip_confirmation": True}}
    assert pending["id"] == "req-1"  # tool_call_id 缺省 → request_id


@pytest.mark.asyncio
@patch("app.core.hitl.orchestrator.session_scope")
async def test_get_pending_no_authorization_becomes_none(mock_scope):
    session = MagicMock()
    mock_scope.return_value = _mock_async_cm(session)
    scalars = MagicMock()
    scalars.first.return_value = _hitl_message(authorization={}, resume=None)
    result = MagicMock()
    result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=result)

    pending = await get_pending_hitl_call({"configurable": {"thread_id": "t-1"}})
    assert pending["authorization"] is None
    assert pending["resume"] is None


@pytest.mark.asyncio
@patch("app.core.hitl.orchestrator.session_scope")
async def test_get_pending_non_json_content_sets_no_request_type(mock_scope):
    session = MagicMock()
    mock_scope.return_value = _mock_async_cm(session)
    msg = _hitl_message()
    msg.content = "not-json"
    scalars = MagicMock()
    scalars.first.return_value = msg
    result = MagicMock()
    result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=result)

    pending = await get_pending_hitl_call({"configurable": {"thread_id": "t-1"}})
    assert pending["request_type"] is None


@pytest.mark.asyncio
@patch("app.core.hitl.orchestrator.session_scope")
async def test_get_pending_missing_thread_id_returns_none(mock_scope):
    assert await get_pending_hitl_call({}) is None
    mock_scope.assert_not_called()


# ============ handle_resume / handle_cancel / close_hitl_message ============


@pytest.mark.asyncio
async def test_handle_resume_normalizes_finalizes_and_clears():
    with (
        patch("app.core.hitl.core.finalize_request", AsyncMock(return_value=True)) as mock_finalize,
        patch("app.core.hitl.orchestrator.get_activity_sink") as mock_get_sink,
    ):
        sink = mock_get_sink.return_value
        sink.clear_human_request = AsyncMock()
        result, claimed = await HITLOrchestrator.handle_resume(
            "t-1",
            {
                "id": "call-1",
                "name": "read_file",
                "args": {"path": "/x"},
                "request_id": "req-1",
                "request_type": "approval",
            },
            "yes",
        )
    assert result == "APPROVED"
    assert claimed is True
    mock_finalize.assert_awaited_once()
    kwargs = mock_finalize.await_args.kwargs
    assert kwargs["thread_id"] == "t-1"
    assert kwargs["request_id"] == "req-1"
    assert kwargs["tool_call_id"] == "call-1"
    assert kwargs["status"] == "completed"
    assert kwargs["response"] == "APPROVED"
    assert kwargs["sibling_key"] == {"name": "read_file", "args": {"path": "/x"}}
    sink.clear_human_request.assert_awaited_once_with("t-1")


@pytest.mark.asyncio
async def test_handle_cancel_finalizes_and_clears():
    with (
        patch("app.core.hitl.core.finalize_request", AsyncMock()) as mock_finalize,
        patch("app.core.hitl.orchestrator.get_activity_sink") as mock_get_sink,
    ):
        sink = mock_get_sink.return_value
        sink.clear_human_request = AsyncMock()
        result = await HITLOrchestrator.handle_cancel(
            "t-1",
            {
                "id": "call-1",
                "name": "ask_confirm",
                "args": {"macro_id": 7},
                "request_id": "req-1",
            },
        )
    assert result == "CANCELLED"
    assert mock_finalize.await_args.kwargs["status"] == "cancelled"
    sink.clear_human_request.assert_awaited_once_with("t-1")


@pytest.mark.asyncio
@patch("app.core.hitl.orchestrator.get_runtime")
async def test_close_hitl_message_success(mock_get_runtime):
    runtime = mock_get_runtime.return_value
    runtime.close_hitl_message = AsyncMock(return_value=True)
    await close_hitl_message("t-1", "call-1")
    runtime.close_hitl_message.assert_awaited_once_with("t-1", "call-1", "completed")


@pytest.mark.asyncio
@patch("app.core.hitl.orchestrator.get_runtime")
async def test_close_hitl_message_missing_warns(mock_get_runtime):
    runtime = mock_get_runtime.return_value
    runtime.close_hitl_message = AsyncMock(return_value=False)
    # 不抛异常，仅记录 warning
    await close_hitl_message("t-1", "call-1")


@pytest.mark.asyncio
@patch("app.core.hitl.orchestrator.get_runtime")
async def test_close_hitl_message_exception_swallowed(mock_get_runtime):
    runtime = mock_get_runtime.return_value
    runtime.close_hitl_message = AsyncMock(
        side_effect=RuntimeError("db down")
    )
    await close_hitl_message("t-1", "call-1")


@pytest.mark.asyncio
@patch("app.core.hitl.orchestrator.session_scope")
async def test_get_pending_query_failure_returns_none(mock_scope):
    mock_scope.side_effect = RuntimeError("db down")
    assert await get_pending_hitl_call({"configurable": {"thread_id": "t-1"}}) is None


def test_normalize_unrecognized_approval_text_passthrough():
    """approval 类型但非确认词 → 原样返回（不强制 APPROVED/REJECTED）。"""
    from app.core.hitl.orchestrator import normalize_hitl_input

    assert (
        normalize_hitl_input({"name": "ask_confirm"}, "请稍等", request_type="approval")
        == "请稍等"
    )


def test_get_pending_request_wrapper_builds_config():
    with patch(
        "app.core.hitl.orchestrator.get_pending_hitl_call",
        AsyncMock(return_value={"name": "x"}),
    ) as mock_call:
        result = None
        import asyncio

        result = asyncio.run(
            HITLOrchestrator.get_pending_request("t-1", "gpt-4o")
        )
    assert result == {"name": "x"}
    assert mock_call.await_args.args[0] == {
        "configurable": {"thread_id": "t-1", "model": "gpt-4o"}
    }


# ============ resolve_approved_tool_result resilience ============


@pytest.mark.asyncio
async def test_confirmation_rejected_returns_localized_text():
    """确认/审批类工具被拒绝（无 authorization）→ 返回描述性本地化拒绝文案，
    而非裸 REJECTED 标记（避免 Agent 偏离主题另起炉灶）。"""
    result = await HITLOrchestrator.resolve_approved_tool_result(
        {
            "id": "call-1",
            "name": "ask_confirm",
            "args": {"action_description": "删除文件"},
        },
        {"metadata": {"project_id": 120}},
        "REJECTED",
        state=None,
    )
    assert "未执行" in result
    assert "ask_confirm" in result


@pytest.mark.asyncio
async def test_confirmation_approved_passthrough():
    """确认/审批类工具被批准（无 authorization）→ 原样返回 APPROVED 令牌。"""
    result = await HITLOrchestrator.resolve_approved_tool_result(
        {
            "id": "call-1",
            "name": "ask_confirm",
            "args": {"action_description": "删除文件"},
        },
        {"metadata": {"project_id": 120}},
        "APPROVED",
        state=None,
    )
    assert result == "APPROVED"


@pytest.mark.asyncio
async def test_free_text_rejected_passthrough_by_request_type():
    """自由文本请求（request_type=text）里 "REJECTED" 是合法文本输入，
    必须原样透传，不得转成描述性拒绝文案。"""
    result = await HITLOrchestrator.resolve_approved_tool_result(
        {
            "id": "call-1",
            "name": "ask_human",
            "request_type": "text",
            "args": {},
        },
        {"metadata": {"project_id": 120}},
        "REJECTED",
        state=None,
    )
    assert result == "REJECTED"


@pytest.mark.asyncio
async def test_grant_persistence_failure_still_reexecutes():
    """grant_permission 失败仅记录 warning，不阻断批准后的重执行。"""
    with (
        patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls,
        patch("app.core.hitl.orchestrator.get_runtime") as mock_get_runtime,
    ):
        mock_auth = AsyncMock()
        mock_auth.grant_permission = AsyncMock(side_effect=RuntimeError("disk full"))
        mock_auth_cls.return_value = mock_auth
        runtime = mock_get_runtime.return_value
        runtime.execute_tool = AsyncMock(return_value="done")

        result = await HITLOrchestrator.resolve_approved_tool_result(
            {
                "id": "call-1",
                "name": "list_dir",
                "args": {"path": "/tmp/outside"},
                "authorization": {"resource_path": "/tmp/outside", "action": "read"},
            },
            {"metadata": {"project_id": 120}},
            "APPROVED",
            state=None,
        )
    assert result == "done"
    runtime.execute_tool.assert_awaited_once()


@pytest.mark.asyncio
async def test_grant_mode_once_does_not_persist_grant():
    """grant_mode=once（仅本次）→ 批准重执行但不持久化授权。"""
    with (
        patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls,
        patch("app.core.hitl.orchestrator.get_runtime") as mock_get_runtime,
    ):
        mock_auth = AsyncMock()
        mock_auth_cls.return_value = mock_auth
        runtime = mock_get_runtime.return_value
        runtime.execute_tool = AsyncMock(return_value="done")

        result = await HITLOrchestrator.resolve_approved_tool_result(
            {
                "id": "call-1",
                "name": "list_dir",
                "args": {"path": "/tmp/outside"},
                "authorization": {"resource_path": "/tmp/outside", "action": "read"},
            },
            {"metadata": {"project_id": 120}},
            "APPROVED",
            state=None,
            grant_mode="once",
        )
    assert result == "done"
    runtime.execute_tool.assert_awaited_once()
    mock_auth.grant_permission.assert_not_awaited()


@pytest.mark.asyncio
async def test_grant_mode_always_persists_permanent_grant():
    """grant_mode=always（总是允许）→ 批准后持久化永久授权（ttl_days=None）。"""
    with (
        patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls,
        patch("app.core.hitl.orchestrator.get_runtime") as mock_get_runtime,
    ):
        mock_auth = AsyncMock()
        mock_auth_cls.return_value = mock_auth
        runtime = mock_get_runtime.return_value
        runtime.execute_tool = AsyncMock(return_value="done")

        result = await HITLOrchestrator.resolve_approved_tool_result(
            {
                "id": "call-1",
                "name": "list_dir",
                "args": {"path": "/tmp/outside"},
                "authorization": {"resource_path": "/tmp/outside", "action": "read"},
            },
            {"metadata": {"project_id": 120}},
            "APPROVED",
            state=None,
            grant_mode="always",
        )
    assert result == "done"
    runtime.execute_tool.assert_awaited_once()
    mock_auth.grant_permission.assert_awaited_once_with(
        resource_path="/tmp/outside",
        action="read",
        scope_type="exact",
        granted_by="hitl-approval",
        ttl_days=None,
    )


@pytest.mark.asyncio
async def test_grant_mode_default_uses_ttl():
    """grant_mode 缺省/None → 维持 TTL grant（默认有效期）。"""
    with (
        patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls,
        patch("app.core.hitl.orchestrator.get_runtime") as mock_get_runtime,
    ):
        mock_auth = AsyncMock()
        mock_auth_cls.return_value = mock_auth
        runtime = mock_get_runtime.return_value
        runtime.execute_tool = AsyncMock(return_value="done")

        result = await HITLOrchestrator.resolve_approved_tool_result(
            {
                "id": "call-1",
                "name": "list_dir",
                "args": {"path": "/tmp/outside"},
                "authorization": {"resource_path": "/tmp/outside", "action": "read"},
            },
            {"metadata": {"project_id": 120}},
            "APPROVED",
            state=None,
        )
    assert result == "done"
    mock_auth.grant_permission.assert_awaited_once()
    call_kwargs = mock_auth.grant_permission.await_args.kwargs
    assert call_kwargs["ttl_days"] is not None


@pytest.mark.asyncio
async def test_macro_default_or_once_does_not_persist_grant():
    """宏（macro_run）默认/once 均不持久化授权（维持"每次执行"语义）。"""
    for gm in ("once", None):
        with (
            patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls,
            patch("app.core.hitl.orchestrator.get_runtime") as mock_get_runtime,
        ):
            mock_auth = AsyncMock()
            mock_auth_cls.return_value = mock_auth
            runtime = mock_get_runtime.return_value
            runtime.execute_tool = AsyncMock(return_value="done")

            await HITLOrchestrator.resolve_approved_tool_result(
                {
                    "id": "call-1",
                    "name": "run_macro",
                    "args": {"macro_id": 7},
                    "authorization": {
                        "resource_path": "macro:7",
                        "action": "macro_run",
                    },
                },
                {"metadata": {"project_id": 120}},
                "APPROVED",
                state=None,
                grant_mode=gm,
            )
            runtime.execute_tool.assert_awaited_once()
            mock_auth.grant_permission.assert_not_awaited()


@pytest.mark.asyncio
async def test_macro_always_persists_macro_scoped_grant():
    """宏（macro_run）+ always → 按宏粒度持久化授权（path=macro:{id}，永久）。"""
    with (
        patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls,
        patch("app.core.hitl.orchestrator.get_runtime") as mock_get_runtime,
    ):
        mock_auth = AsyncMock()
        mock_auth_cls.return_value = mock_auth
        runtime = mock_get_runtime.return_value
        runtime.execute_tool = AsyncMock(return_value="done")

        result = await HITLOrchestrator.resolve_approved_tool_result(
            {
                "id": "call-1",
                "name": "run_macro",
                "args": {"macro_id": 7},
                "authorization": {
                    "resource_path": "macro:7",
                    "action": "macro_run",
                },
            },
            {"metadata": {"project_id": 120}},
            "APPROVED",
            state=None,
            grant_mode="always",
        )
    assert result == "done"
    mock_auth.grant_permission.assert_awaited_once_with(
        resource_path="macro:7",
        action="macro_run",
        scope_type="exact",
        granted_by="hitl-approval",
        ttl_days=None,
    )


@pytest.mark.asyncio
async def test_grant_persisted_under_authorization_project_id():
    """授权落库项目以 authorization.project_id（宏归属项目）为准，非会话项目。

    修复跨项目调用宏：写侧按宏归属项目持久化，才能与
    ``is_macro_permanently_granted(macro.project_id, ...)`` 读取端闭合。
    """
    with (
        patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls,
        patch("app.core.hitl.orchestrator.get_runtime") as mock_get_runtime,
    ):
        mock_auth = AsyncMock()
        mock_auth_cls.return_value = mock_auth
        runtime = mock_get_runtime.return_value
        runtime.execute_tool = AsyncMock(return_value="done")

        result = await HITLOrchestrator.resolve_approved_tool_result(
            {
                "id": "call-1",
                "name": "run_macro",
                "args": {"macro_id": 7},
                "authorization": {
                    "resource_path": "macro:7",
                    "action": "macro_run",
                    "project_id": 88,
                },
            },
            {"metadata": {"project_id": 120}},
            "APPROVED",
            state=None,
            grant_mode="always",
        )
    assert result == "done"
    mock_auth_cls.assert_called_once_with(88)
    mock_auth.grant_permission.assert_awaited_once_with(
        resource_path="macro:7",
        action="macro_run",
        scope_type="exact",
        granted_by="hitl-approval",
        ttl_days=None,
    )


@pytest.mark.asyncio
async def test_reexecution_failure_returns_error_text():
    """重执行抛异常 → 返回错误文本（不向上抛，避免循环卡死）。"""
    with (
        patch("app.core.hitl.authorization.AuthorizationService") as mock_auth_cls,
        patch("app.core.hitl.orchestrator.get_runtime") as mock_get_runtime,
    ):
        mock_auth = AsyncMock()
        mock_auth_cls.return_value = mock_auth
        runtime = mock_get_runtime.return_value
        runtime.execute_tool = AsyncMock(side_effect=RuntimeError("boom"))

        result = await HITLOrchestrator.resolve_approved_tool_result(
            {
                "id": "call-1",
                "name": "list_dir",
                "args": {"path": "/tmp/outside"},
                "authorization": {"resource_path": "/tmp/outside", "action": "read"},
            },
            {"metadata": {"project_id": 120}},
            "APPROVED",
            state=None,
        )
    assert result == "[HITL Re-execution Failed] boom"
