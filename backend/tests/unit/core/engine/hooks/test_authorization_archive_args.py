"""authorization_gate 存档 args 保真：ToolInput extra 字段必须进入审批存档。

回归背景：ToolInput（extra="allow"）把 edit 的 target/replacement 承载在
model_extra，而审批存档原实现只搬运 ``args`` 字段 + command/path/content/
query 白名单——edit 批准后重执行 Args 只剩 path，报缺参 SYSTEM ERROR
（write/bash 恰好被白名单覆盖才显得"部分工具正常"）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.engine.hooks.authorization import authorization_gate
from app.core.engine.hooks.core import HookContext
from app.core.engine.hooks.schemas import ToolInput
from app.core.hitl.authorization import AuthorizationService


def _hitl_ctx(tool_name: str, tool_input: ToolInput) -> HookContext:
    return HookContext(
        thread_id="t-archive",
        run_id="r-1",
        project_id=1,
        tool_name=tool_name,
        tool_input=tool_input,
        tool_use_id="call-archive",
    )




@pytest.mark.asyncio
async def test_edit_extra_fields_archived():
    """edit 的 target/replacement（model_extra）必须进入存档 args。"""
    captured: dict = {}

    service = MagicMock(spec=AuthorizationService)
    service.evaluate = AsyncMock(return_value=None)
    service._load = AsyncMock(return_value=None)
    service._granted = []
    service.request_authorization = AsyncMock(
        side_effect=lambda **kw: (
            captured.update(args=kw.get("original_tool_args")),
            "req-1",
        )[1]
    )
    service_patch = patch(
        "app.core.engine.hooks.authorization.AuthorizationService",
        return_value=service,
    )
    was_patch = patch(
        "app.core.engine.hooks.authorization.HITLOrchestrator.was_call_recently_approved",
        new=AsyncMock(return_value=False),
    )
    i18n_patch = patch(
        "app.i18n.service.SystemConfigService.get_value", return_value="zh"
    )
    ctx = _hitl_ctx(
        "edit",
        ToolInput(
            path="/tmp/x/rollback-a.txt",
            target="BEFORE-A",
            replacement="AFTER-A",
        ),
    )
    with service_patch, was_patch, i18n_patch:
        await authorization_gate(ctx)

    args = captured.get("args") or {}
    assert args.get("path") == "/tmp/x/rollback-a.txt"
    assert args.get("target") == "BEFORE-A"
    assert args.get("replacement") == "AFTER-A"


@pytest.mark.asyncio
async def test_write_whitelist_still_works():
    """回归：write 的 content 白名单路径不受影响。"""
    captured: dict = {}

    service = MagicMock(spec=AuthorizationService)
    service.evaluate = AsyncMock(return_value=None)
    service._load = AsyncMock(return_value=None)
    service._granted = []
    service.request_authorization = AsyncMock(
        side_effect=lambda **kw: (
            captured.update(args=kw.get("original_tool_args")),
            "req-1",
        )[1]
    )
    service_patch = patch(
        "app.core.engine.hooks.authorization.AuthorizationService",
        return_value=service,
    )
    was_patch = patch(
        "app.core.engine.hooks.authorization.HITLOrchestrator.was_call_recently_approved",
        new=AsyncMock(return_value=False),
    )
    i18n_patch = patch(
        "app.i18n.service.SystemConfigService.get_value", return_value="zh"
    )
    ctx = _hitl_ctx(
        "write",
        ToolInput(path="/tmp/x/new.txt", content="HELLO"),
    )
    with service_patch, was_patch, i18n_patch:
        await authorization_gate(ctx)

    args = captured.get("args") or {}
    assert args.get("path") == "/tmp/x/new.txt"
    assert args.get("content") == "HELLO"


def test_tool_input_extra_merge_precedence():
    """显式 args 字段优先于 model_extra 同名键（防御性合并顺序锁定）。"""
    ti = ToolInput.model_validate(
        {"path": "/x", "args": {"k": "from-args"}, "k": "from-extra"}
    )
    merged = {**(ti.model_extra or {}), **(ti.args or {})}
    assert merged["k"] == "from-args"
    assert "path" not in ti.model_extra
