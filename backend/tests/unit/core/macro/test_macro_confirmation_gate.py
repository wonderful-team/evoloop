"""Tests for run_macro high-risk confirmation gate.

Verifies that macros with requires_confirmation=True trigger a HITL approval
before execution, that skip_confirmation=True bypasses the gate, and that the
gate does NOT hardcode skip_grant (persistence is driven by resume grant_mode:
always→按宏粒度写盘，once/默认→不写盘).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.engine.tools.react_macro import _run_macro_row


def _fake_macro(requires_confirmation: bool = True) -> MagicMock:
    macro = MagicMock()
    macro.id = 979
    macro.name = "改余额{query}"
    macro.risk_tier = "money"
    macro.project_id = 120
    macro.requires_confirmation = requires_confirmation
    return macro


@pytest.mark.asyncio
async def test_confirmation_gate_triggers_hitl():
    """requires_confirmation=true 且未豁免 → 触发 HITL 确认，不直接执行宏。"""
    macro = _fake_macro()
    ctx = MagicMock()
    ctx.project_id = 120
    ctx.command_id = "cmd-1"
    ctx.current_tool_call_id = "call-1"
    ctx.last_ai_message_id = "msg-1"

    with patch(
        "app.core.engine.tools.react_macro.load_macro",
        AsyncMock(return_value=macro),
    ), patch(
        "app.core.context.manager.ContextManager.current",
        return_value=ctx,
    ), patch(
        "app.core.hitl.orchestrator.HITLOrchestrator.raise_approval",
        AsyncMock(side_effect=InterruptSentinel),
    ) as mock_raise, patch(
        "app.core.engine.tools.react_macro.MacroEngine.run",
        AsyncMock(),
    ) as mock_engine:

        with pytest.raises(InterruptSentinel):
            await _run_macro_row(979, None, {"query": "u1"}, "thread-1")

    mock_raise.assert_awaited_once()
    # 确认请求不再硬编码 skip_grant：由 resume 端 grant_mode 决定是否持久化授权
    # （always→按宏粒度写盘；once/默认→不写盘）。请求不带 skip_grant 标记。
    kwargs = mock_raise.await_args.kwargs
    assert "skip_grant" not in kwargs
    assert kwargs["original_tool_name"] == "run_macro"
    assert kwargs["resource_path"] == "macro:979"
    assert kwargs["tool_name"] == "run_macro"
    # 写侧授权元数据必须与读侧 is_granted(macro:{id}, "macro_run") 闭合：
    # 授权按宏归属项目持久化（macro.project_id），非会话项目。
    assert kwargs["action"] == "macro_run"
    assert kwargs["project_id"] == 120
    # 未批准前不执行宏引擎
    mock_engine.assert_not_awaited()


@pytest.mark.asyncio
async def test_skip_confirmation_bypasses_gate():
    """skip_confirmation=True（运营已豁免）→ 直接执行宏，不触发确认。"""
    macro = _fake_macro()

    with patch(
        "app.core.engine.tools.react_macro.find_macro_by_name",
        AsyncMock(return_value=macro),
    ), patch(
        "app.core.engine.tools.react_macro.resolve_project_base_url",
        AsyncMock(return_value="http://127.0.0.1:9003"),
    ), patch(
        "app.core.engine.tools.react_macro.MacroEngine.run",
        AsyncMock(
            return_value=MagicMock(
                status="ok",
                success=True,
                message="done",
                extracted_data={"verify_status": "VERIFY:待转账"},
                fallback_context=None,
                suggestions=[],
            )
        ),
    ) as mock_engine:

        result = await _run_macro_row(None, "改余额{query}", {"query": "u1"}, "thread-1", skip_confirmation=True)

    assert "改余额" in result
    mock_engine.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_confirmation_macro_skips_gate():
    """requires_confirmation=false 的宏 → 不触发确认，直接执行。"""
    macro = _fake_macro(requires_confirmation=False)

    with patch(
        "app.core.engine.tools.react_macro.load_macro",
        AsyncMock(return_value=macro),
    ), patch(
        "app.core.engine.tools.react_macro.resolve_project_base_url",
        AsyncMock(return_value="http://127.0.0.1:9003"),
    ), patch(
        "app.core.engine.tools.react_macro.MacroEngine.run",
        AsyncMock(
            return_value=MagicMock(
                status="ok",
                success=True,
                message="done",
                extracted_data=None,
                fallback_context=None,
                suggestions=[],
            )
        ),
    ) as mock_engine:

        result = await _run_macro_row(979, None, None, "thread-1")

    assert "改余额" in result
    mock_engine.assert_awaited_once()


@pytest.mark.asyncio
async def test_macro_gate_reuses_existing_pending():
    """同线程同宏同参数已有 pending 请求 → 复用，不创建新请求。"""
    macro = _fake_macro()
    ctx = MagicMock()
    ctx.project_id = 120
    ctx.command_id = "cmd-1"
    ctx.current_tool_call_id = "call-1"
    ctx.last_ai_message_id = "msg-1"
    existing = {"request_id": "req-macro-existing", "context": ""}

    with patch(
        "app.core.engine.tools.react_macro.load_macro",
        AsyncMock(return_value=macro),
    ), patch(
        "app.core.context.manager.ContextManager.current",
        return_value=ctx,
    ), patch(
        "app.core.hitl.core._find_pending_by_key",
        AsyncMock(return_value=existing),
    ), patch(
        "app.core.hitl.orchestrator.HITLOrchestrator.raise_approval",
        AsyncMock(),
    ) as mock_raise, patch(
        "app.core.engine.tools.react_macro.raise_hitl_interrupt",
        side_effect=InterruptSentinel,
    ) as mock_interrupt:

        with pytest.raises(InterruptSentinel):
            await _run_macro_row(979, None, {"query": "u1"}, "thread-1")

    # 复用已有请求：不创建新请求、不推送，用已有 request_id 挂起
    mock_raise.assert_not_awaited()
    mock_interrupt.assert_called_once()
    assert mock_interrupt.call_args.args[0] == "req-macro-existing"


@pytest.mark.asyncio
async def test_macro_gate_reuses_recently_approved():
    """同线程同宏同参数最近已批准 → 不创建新请求，直接执行宏（复用批准语义，
    避免 Supervisor 循环：旧行为只返回"已确认过"提示不执行，Agent 会困惑重试）。"""
    macro = _fake_macro()
    ctx = MagicMock()
    ctx.project_id = 120
    ctx.command_id = "cmd-1"
    ctx.current_tool_call_id = "call-1"
    ctx.last_ai_message_id = "msg-1"

    with patch(
        "app.core.engine.tools.react_macro.load_macro",
        AsyncMock(return_value=macro),
    ), patch(
        "app.core.engine.tools.react_macro.resolve_tool_context",
        return_value={
            "project_id": 120,
            "command_id": "cmd-1",
            "tool_call_id": "call-1",
            "parent_id": "msg-1",
        },
    ), patch(
        "app.core.hitl.core._find_pending_by_key",
        AsyncMock(return_value=None),
    ), patch(
        "app.core.hitl.core.find_recently_approved_by_key",
        AsyncMock(return_value="req-approved-1"),
    ), patch(
        "app.core.hitl.orchestrator.HITLOrchestrator.raise_approval",
        AsyncMock(),
    ) as mock_raise, patch(
        "app.core.engine.tools.react_macro.MacroEngine.run",
        AsyncMock(
            return_value=MagicMock(
                status="ok",
                success=True,
                message="done",
                extracted_data=None,
                fallback_context=None,
                suggestions=[],
            )
        ),
    ) as mock_engine:

        result = await _run_macro_row(979, None, {"query": "u1"}, "thread-1")

    # 不创建新确认请求，直接执行宏
    mock_raise.assert_not_awaited()
    mock_engine.assert_awaited_once()
    assert "改余额" in result


class InterruptSentinel(Exception):
    """Sentinel exception to simulate raise_hitl_interrupt."""
