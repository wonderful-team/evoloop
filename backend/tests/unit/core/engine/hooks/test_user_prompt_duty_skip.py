"""值守唤醒跳过兜底域分类的契约测试（2026-09-23 实测事故回归）。

事故链：dispatcher resolve_wakeup_domain 对 pid=0 fail-open 后不再携带
intent_hint → user_prompt_submit_handler 兜底跑 L1 → 按措辞把 Upwork 侦察
任务猜成 ecommerce 域 → 商城 profile 的 native_tools 白名单裁掉 bash/文件
工具、Agent Reach 被域过滤藏出技能索引 → Agent 只剩 webfetch 死循环。

契约：metadata.source == "duty" 的请求一律跳过兜底分类；其余入口行为不变。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.engine.hooks.core import HookContext
from app.core.engine.hooks.handlers.user import user_prompt_submit_handler
from app.core.routing.schemas import RouteDecision


def _ctx(source: str) -> HookContext:
    ctx = HookContext(thread_id="t-test")
    ctx.metadata["prompt"] = "翻 Upwork 最新挂单，找出 AI 客服相关的活"
    ctx.metadata["source"] = source
    ctx.project_id = 0
    return ctx


@pytest.mark.asyncio
async def test_duty_wakeup_skips_l0_classification():
    """source=duty → 不跑 L1 分类、不挂 intent_hint（dispatcher 权威）。"""
    ctx = _ctx("duty")
    with patch(
        "app.core.engine.hooks.handlers.user.command_router.resolve",
        new=AsyncMock(side_effect=AssertionError("duty run must not classify")),
    ) as spy:
        result = await user_prompt_submit_handler(ctx)

    assert result.success
    spy.assert_not_awaited()
    assert ctx.metadata.get("intent_hint") is None


@pytest.mark.asyncio
async def test_chat_entry_still_classifies():
    """普通 chat 入口行为不变：分类结果照常挂载。"""
    ctx = _ctx("chat")
    decision = RouteDecision(intent_hint=None)
    with patch(
        "app.core.engine.hooks.handlers.user.command_router.resolve",
        new=AsyncMock(return_value=decision),
    ):
        result = await user_prompt_submit_handler(ctx)

    assert result.success
    assert ctx.metadata.get("intent_hint") is None
