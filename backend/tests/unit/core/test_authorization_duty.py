"""Tests for authorization_gate duty thread HITL flow.

Verifies that duty threads (``duty_`` prefix) also go through the HITL approval
flow (no auto-reject) — sensitive operations must be approved by an operator
even in unattended duty mode.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.engine.hooks.authorization import authorization_gate
from app.core.engine.hooks.core import HookContext
from app.core.engine.hooks.schemas import ToolInput


def _ctx(thread_id: str) -> HookContext:
    return HookContext(
        thread_id=thread_id,
        run_id="run-1",
        project_id=120,
        tool_name="list_dir",
        tool_input=ToolInput.model_validate({"path": "/Users/huangjinhuan/www/mall-backend"}),
        tool_use_id="call-1",
    )


@pytest.mark.asyncio
async def test_duty_thread_outside_path_goes_hitl():
    """值守线程越界访问 → 走 HITL（不 auto-reject），运营人员远程批准。"""
    ctx = _ctx("duty_120_contact1")

    with patch(
        "app.core.engine.hooks.authorization._is_path_safe",
        return_value=False,
    ), patch(
        "app.core.engine.hooks.authorization.AuthorizationService",
    ) as mock_cls:
        mock_svc = AsyncMock()
        mock_svc.evaluate = AsyncMock(return_value=type(
            "D", (), {"approved": False, "requires_hitl": True, "policy": None}
        )())
        mock_svc._load = AsyncMock()
        mock_svc._granted = []
        mock_svc.request_authorization = AsyncMock()
        mock_cls.return_value = mock_svc

        # 值守 → 与普通线程一致走 HITL 分支（request_authorization 被调用）
        with patch(
            "app.core.engine.hooks.authorization.AuthorizationPolicy",
        ), patch(
            "app.core.engine.hooks.authorization.AuthorizationDecision",
        ) as mock_dec:
            mock_dec.return_value = type(
                "Dec", (), {
                    "approved": False,
                    "requires_hitl": True,
                    "reason": "needs approval",
                    "policy": type("P", (), {"risk_level": "high"})(),
                    "resource_path": "/Users/huangjinhuan/www/mall-backend",
                    "action": "read",
                }
            )()
            await authorization_gate(ctx)

    mock_svc.request_authorization.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_duty_thread_outside_path_still_hitl():
    """非值守（web 用户）越界访问 → 仍走 HITL 弹窗（不 auto-reject）。"""
    ctx = _ctx("web-abc-123")

    with patch(
        "app.core.engine.hooks.authorization._is_path_safe",
        return_value=False,
    ), patch(
        "app.core.engine.hooks.authorization.AuthorizationService",
    ) as mock_cls:
        mock_svc = AsyncMock()
        mock_svc.evaluate = AsyncMock(return_value=type(
            "D", (), {"approved": False, "requires_hitl": True, "policy": None}
        )())
        mock_svc._load = AsyncMock()
        mock_svc._granted = []
        mock_svc.request_authorization = AsyncMock()
        mock_cls.return_value = mock_svc

        # 非值守 → 走 HITL 分支（request_authorization 被调用）
        with patch(
            "app.core.engine.hooks.authorization.AuthorizationPolicy",
        ), patch(
            "app.core.engine.hooks.authorization.AuthorizationDecision",
        ) as mock_dec:
            mock_dec.return_value = type(
                "Dec", (), {
                    "approved": False,
                    "requires_hitl": True,
                    "reason": "needs approval",
                    "policy": type("P", (), {"risk_level": "high"})(),
                    "resource_path": "/Users/huangjinhuan/www/mall-backend",
                    "action": "read",
                }
            )()
            await authorization_gate(ctx)

    mock_svc.request_authorization.assert_awaited_once()
