"""Tests for HITL core primitives: request lifecycle, notification, interrupt."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import AgentHumanInterruptException
from app.core.hitl.core import (
    HumanInputRequest,
    cancel_request,
    get_pending_requests_for_thread,
    push_hitl_notification,
    raise_hitl_interrupt,
)


def _mock_async_cm(return_value):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=return_value)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ============ HumanInputRequest.from_db ============


def _db_request(**overrides) -> MagicMock:
    req = MagicMock()
    req.id = "req-1"
    req.thread_id = "t-1"
    req.type = "approval"
    req.description = "approve?"
    req.options = ["yes", "no"]
    req.context = "ctx"
    req.default_value = "REJECTED"
    req.created_at = datetime.utcnow()
    req.status = "pending"
    req.result = None
    for k, v in overrides.items():
        setattr(req, k, v)
    return req


def test_from_db_maps_fields():
    model = HumanInputRequest.from_db(_db_request())
    assert model.id == "req-1"
    assert model.request_type == "approval"
    assert model.prompt == "approve?"
    assert model.options == ["yes", "no"]
    assert model.default_value == "REJECTED"
    assert model.status == "pending"


# ============ get_pending_requests_for_thread / cancel_request ============


@pytest.mark.asyncio
@patch("app.core.hitl.core.session_scope")
async def test_get_pending_requests_for_thread(mock_scope):
    session = MagicMock()
    mock_scope.return_value = _mock_async_cm(session)
    scalars = MagicMock()
    scalars.all.return_value = [_db_request(id="req-1"), _db_request(id="req-2")]
    result = MagicMock()
    result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=result)

    requests = await get_pending_requests_for_thread("t-1")
    assert [r.id for r in requests] == ["req-1", "req-2"]
    stmt = session.execute.await_args.args[0]
    # WHERE 同时限定 thread_id 与 pending 状态
    assert "human_requests.thread_id" in str(stmt)
    assert "human_requests.status = :status_1" in str(stmt)


@pytest.mark.asyncio
@patch("app.core.hitl.core.session_scope")
async def test_cancel_request_success(mock_scope):
    session = MagicMock()
    mock_scope.return_value = _mock_async_cm(session)
    result = MagicMock()
    result.rowcount = 1
    session.execute = AsyncMock(return_value=result)

    assert await cancel_request("req-1") is True


@pytest.mark.asyncio
@patch("app.core.hitl.core.session_scope")
async def test_cancel_request_no_pending_row(mock_scope):
    session = MagicMock()
    mock_scope.return_value = _mock_async_cm(session)
    result = MagicMock()
    result.rowcount = 0
    session.execute = AsyncMock(return_value=result)

    assert await cancel_request("req-1") is False


# ============ push_hitl_notification ============


def _request() -> HumanInputRequest:
    return HumanInputRequest(
        id="req-1",
        thread_id="t-1",
        request_type="approval",
        prompt="approve?",
        context="ctx",
        default_value="REJECTED",
    )


@pytest.mark.asyncio
@patch("app.core.hitl.core.get_activity_sink")
@patch("app.core.hitl.core.get_runtime")
async def test_push_notification_assembles_metadata(mock_get_runtime, mock_get_sink):
    runtime = mock_get_runtime.return_value
    runtime.push_hitl_request = MagicMock()
    sink = mock_get_sink.return_value
    sink.set_human_request = AsyncMock()

    await push_hitl_notification(
        thread_id="t-1",
        request=_request(),
        request_data={"type": "approval", "prompt": "approve?"},
        project_id=120,
        run_id="r-1",
        tool_name="mcp__ops__transfer",
        tool_call_id="call-1",
        parent_id="m-1",
        original_tool_name="mcp__ops__transfer",
        original_tool_args={"transfer_id": 244},
        resource_path="macro:7",
        action="macro_run",
        skip_grant=True,
        resume_override={"args": {"skip_confirmation": True}},
    )

    sink.set_human_request.assert_awaited_once_with(
        thread_id="t-1", request_data={"type": "approval", "prompt": "approve?"}
    )
    kwargs = runtime.push_hitl_request.call_args.kwargs
    meta = kwargs["metadata"]
    assert meta["original_tool"] == {
        "name": "mcp__ops__transfer",
        "args": {"transfer_id": 244},
    }
    assert meta["authorization"] == {
        "resource_path": "macro:7",
        "action": "macro_run",
        "project_id": 120,
        "skip_grant": True,
    }
    assert meta["resume"] == {"args": {"skip_confirmation": True}}
    assert kwargs["tool_call_id"] == "call-1"
    assert kwargs["tool_name"] == "mcp__ops__transfer"


@pytest.mark.asyncio
@patch("app.core.hitl.core.get_activity_sink")
@patch("app.core.hitl.core.get_runtime")
async def test_push_notification_minimal_metadata(mock_get_runtime, mock_get_sink):
    runtime = mock_get_runtime.return_value
    runtime.push_hitl_request = MagicMock()
    sink = mock_get_sink.return_value
    sink.set_human_request = AsyncMock()

    await push_hitl_notification(
        thread_id="t-1",
        request=_request(),
        request_data={},
    )

    kwargs = runtime.push_hitl_request.call_args.kwargs
    assert kwargs["metadata"] is None
    assert kwargs["tool_name"] == "approval"  # tool_name 缺省为 request_type


@pytest.mark.asyncio
@patch("app.core.hitl.core.get_activity_sink")
@patch("app.core.hitl.core.get_runtime")
async def test_push_notification_handler_failure_swallowed(
    mock_get_runtime, mock_get_sink
):
    """EngineRuntime 失败只记录 warning，不阻断 activity 通知。"""
    runtime = mock_get_runtime.return_value
    runtime.push_hitl_request = MagicMock(side_effect=RuntimeError("handler boom"))
    sink = mock_get_sink.return_value
    sink.set_human_request = AsyncMock()

    await push_hitl_notification(
        thread_id="t-1",
        request=_request(),
        request_data={},
    )
    sink.set_human_request.assert_awaited_once()


def test_raise_hitl_interrupt_raises_with_request_id():
    with pytest.raises(AgentHumanInterruptException) as exc_info:
        raise_hitl_interrupt("req-1", "waiting")
    assert exc_info.value.request_id == "req-1"


def test_human_input_request_defaults():
    model = HumanInputRequest(id="r", thread_id="t", request_type="text", prompt="p")
    assert model.status == "pending"
    assert model.options is None
    assert model.response is None
    assert model.created_at is not None


# ============ create_request ============


@pytest.mark.asyncio
@patch("app.core.hitl.core.session_scope")
async def test_create_request_accepts_multi_choice(mock_scope):
    """multi_choice 是合法请求类型：成功创建并持久化。"""
    session = MagicMock()
    mock_scope.return_value = _mock_async_cm(session)

    async def _flush():
        session.add.call_args.args[0].created_at = datetime.utcnow()

    session.flush = AsyncMock(side_effect=_flush)

    from app.core.hitl.core import create_request

    req = await create_request(
        "t-1",
        "multi_choice",
        "请勾选要处理的退款工单",
        options=["全部", "仅待转账", "仅申请售后", "暂不处理"],
    )
    assert req.request_type == "multi_choice"
    assert req.options == ["全部", "仅待转账", "仅申请售后", "暂不处理"]
    # 持久化到 DB 的 type 列
    persisted = session.add.call_args.args[0]
    assert persisted.type == "multi_choice"
    assert persisted.status == "pending"


@pytest.mark.asyncio
@patch("app.core.hitl.core.session_scope")
async def test_create_request_rejects_invalid_type(mock_scope):
    """非 HumanRequestType 枚举值 → fail-fast 抛 ValueError，不落库。"""
    from app.core.hitl.core import create_request

    with pytest.raises(ValueError):
        await create_request("t-1", "bogus_type", "p")
    mock_scope.assert_not_called()


@pytest.mark.asyncio
@patch("app.core.hitl.core.session_scope")
async def test_create_request_multi_choice_without_options_is_allowed_shape(
    mock_scope,
):
    """multi_choice 允许 options 为空（工具层负责校验），核心层只校验类型合法。"""
    session = MagicMock()
    mock_scope.return_value = _mock_async_cm(session)

    added = {}

    async def _flush():
        obj = session.add.call_args.args[0]
        obj.created_at = datetime.utcnow()
        added["obj"] = obj

    session.flush = AsyncMock(side_effect=_flush)

    from app.core.hitl.core import create_request

    req = await create_request("t-1", "multi_choice", "p")
    assert req.request_type == "multi_choice"
    assert req.options is None
    assert added["obj"].type == "multi_choice"


# ============ finalize_request sibling 分支 ============


@pytest.mark.asyncio
@patch("app.core.hitl.core.session_scope")
async def test_sibling_close_skipped_without_name(mock_scope):
    """sibling_key 缺 name → 不查询兄弟请求。"""
    session = MagicMock()
    mock_scope.return_value = _mock_async_cm(session)
    req_result = MagicMock()
    req_result.rowcount = 1
    msg_result = MagicMock()
    msg_result.rowcount = 1
    session.execute = AsyncMock(side_effect=[req_result, msg_result])

    from app.core.hitl.core import finalize_request

    ok = await finalize_request(
        thread_id="t-1",
        request_id="req-1",
        tool_call_id="call-1",
        status="completed",
        sibling_key={"args": {"x": 1}},
    )
    assert ok is True
    assert session.execute.await_count == 2  # 未触发兄弟查询


@pytest.mark.asyncio
@patch("app.core.hitl.core.session_scope")
async def test_sibling_close_ignores_different_original_tool(mock_scope):
    """兄弟消息 original_tool.name 不同 → 跳过。"""
    session = MagicMock()
    mock_scope.return_value = _mock_async_cm(session)

    def _sibling(**meta):
        s = MagicMock()
        s.meta_data = meta
        return s

    scalars = MagicMock()
    scalars.all.return_value = [
        _sibling(
            original_tool={"name": "other_tool", "args": {"x": 1}},
            hitl_request_id="s-req",
        ),
    ]
    result = MagicMock()
    result.scalars.return_value = scalars
    req_result = MagicMock()
    req_result.rowcount = 1
    msg_result = MagicMock()
    msg_result.rowcount = 1
    session.execute = AsyncMock(side_effect=[req_result, msg_result, result])

    from app.core.hitl.core import finalize_request

    await finalize_request(
        thread_id="t-1",
        request_id="req-1",
        tool_call_id="call-1",
        status="completed",
        sibling_key={"name": "read_file", "args": {"x": 1}},
    )
    # 兄弟 name 不匹配 → 无额外 update 执行（总调用数仍为 3：req/msg/兄弟查询）
    assert session.execute.await_count == 3


@pytest.mark.asyncio
@patch("app.core.hitl.core.session_scope")
async def test_sibling_close_exception_does_not_block_finalize(mock_scope):
    """兄弟关闭失败仅记录 warning，不阻断主流程。"""
    session = MagicMock()
    mock_scope.return_value = _mock_async_cm(session)
    req_result = MagicMock()
    req_result.rowcount = 1
    msg_result = MagicMock()
    msg_result.rowcount = 1
    session.execute = AsyncMock(
        side_effect=[req_result, msg_result, RuntimeError("sibling query boom")]
    )

    from app.core.hitl.core import finalize_request

    ok = await finalize_request(
        thread_id="t-1",
        request_id="req-1",
        tool_call_id="call-1",
        status="completed",
        sibling_key={"name": "read_file", "args": {"x": 1}},
    )
    assert ok is True
