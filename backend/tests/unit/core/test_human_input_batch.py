"""Unit tests for ask_confirm approval path and ask_human selection flows.

ask_confirm 现在只走统一单动作审批（HITLOrchestrator.raise_approval）；批量审批
（batch grants）已随 batch_grants 移除——宏的免打扰由
``AuthorizationService.is_granted``（grant_mode=always 永久授权）与
``find_recently_approved_by_key``（同参最近批准去重）承担。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.context.manager import ContextManager, EvoContext
from app.core.exceptions import AgentHumanInterruptException


def _ctx(**overrides):
    return EvoContext(
        request_id="req-1",
        thread_id="t-1",
        project_id=120,
        command_id=1,
        current_tool_call_id="call-1",
        last_ai_message_id="msg-1",
        **overrides,
    )


@pytest.mark.asyncio
async def test_ask_confirm_uses_single_approval(monkeypatch):
    """ask_confirm 始终走 HITLOrchestrator.raise_approval（统一审批路径）。"""
    from app.core.hitl.orchestrator import HITLOrchestrator
    from app.core.hitl.tools import ask_confirm

    async def _raise_approval(**_):
        raise AgentHumanInterruptException("req-single", "text")

    monkeypatch.setattr(HITLOrchestrator, "raise_approval", _raise_approval)

    with ContextManager.use(_ctx()), pytest.raises(AgentHumanInterruptException):
        await ask_confirm(action_description="单操作", risk_level="medium")


# ============ ask_human multi_choice ============


def _ctx_multi(**overrides):
    return EvoContext(
        request_id="req-1",
        thread_id="t-mc",
        project_id=120,
        command_id=1,
        current_tool_call_id="call-mc",
        last_ai_message_id="msg-mc",
        **overrides,
    )


def _patch_ask_human_primitives(monkeypatch):
    from app.core.hitl import tools as hi

    def _raise_interrupt(rid, rt):
        raise AgentHumanInterruptException(rid, rt)

    monkeypatch.setattr(hi, "create_request", AsyncMock(return_value=MagicMock(id="req-mc")))
    monkeypatch.setattr(hi, "push_hitl_notification", AsyncMock())
    monkeypatch.setattr(hi, "raise_hitl_interrupt", _raise_interrupt)
    return hi


@pytest.mark.asyncio
async def test_ask_human_multi_choice_requires_options(monkeypatch):
    """multi_choice 无 options → 返回错误文案，不发起请求。"""
    hi = _patch_ask_human_primitives(monkeypatch)

    with ContextManager.use(_ctx_multi()):
        res = await hi.ask_human("勾选处理哪些", input_type="multi_choice", options=None)

    assert isinstance(res, str) and res
    hi.create_request.assert_not_called()


@pytest.mark.asyncio
async def test_ask_human_multi_choice_creates_request_with_options(monkeypatch):
    """multi_choice 带 options → 以 multi_choice 类型创建请求并中断。"""
    hi = _patch_ask_human_primitives(monkeypatch)
    options = ["全部", "仅待转账", "仅申请售后", "暂不处理"]

    with ContextManager.use(_ctx_multi()), pytest.raises(AgentHumanInterruptException):
        await hi.ask_human(
            "请勾选要处理的退款工单",
            input_type="multi_choice",
            options=options,
        )

    hi.create_request.assert_awaited_once()
    kwargs = hi.create_request.await_args.kwargs
    assert kwargs["request_type"] == "multi_choice"
    assert kwargs["options"] == options
    assert kwargs["prompt"] == "请勾选要处理的退款工单"
    hi.push_hitl_notification.assert_awaited_once()


@pytest.mark.asyncio
async def test_ask_human_choice_still_single(monkeypatch):
    """choice（单选）语义不受影响。"""
    hi = _patch_ask_human_primitives(monkeypatch)

    with ContextManager.use(_ctx_multi()), pytest.raises(AgentHumanInterruptException):
        await hi.ask_human("单选一个", input_type="choice", options=["A", "B"])

    kwargs = hi.create_request.await_args.kwargs
    assert kwargs["request_type"] == "choice"
