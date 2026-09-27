"""Unit tests: EXECUTION_MODE=docker 时 HITL 全程豁免（无中断、无请求落库）。

覆盖中心守卫（hitl_enabled / auto_hitl_response / raise_hitl_interrupt），
以及暴露给 Agent 的三个触发面：ask_human、ask_confirm、run_macro 高风险确认。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.core.engine.tools import react_macro as run_macro_mod
from app.core.exceptions import AgentHumanInterruptException
from app.core.hitl.core import (
    auto_hitl_response,
    hitl_enabled,
    raise_hitl_interrupt,
)
from app.core.hitl.orchestrator import HITLOrchestrator
from app.core.hitl.tools import ask_confirm, ask_human


class TestHitlEnabledGuard:
    def test_enabled_in_local(self, monkeypatch):
        monkeypatch.setattr(settings, "EXECUTION_MODE", "local")
        assert hitl_enabled() is True

    def test_disabled_in_docker(self, monkeypatch):
        monkeypatch.setattr(settings, "EXECUTION_MODE", "docker")
        assert hitl_enabled() is False


class TestAutoHitlResponse:
    @pytest.mark.parametrize(
        "request_type",
        ["approval", "confirmation"],
    )
    def test_approval_family_auto_approved(self, request_type):
        assert auto_hitl_response(request_type) == "APPROVED"

    def test_prefers_default_value(self):
        assert auto_hitl_response("text", default_value="yes") == "yes"

    def test_uses_first_option_when_no_default(self):
        assert auto_hitl_response("choice", options=["a", "b"]) == "a"

    def test_empty_fallback(self):
        assert auto_hitl_response("text") == ""


class TestRaiseHitlInterrupt:
    def test_raises_in_local(self, monkeypatch):
        monkeypatch.setattr(settings, "EXECUTION_MODE", "local")
        with pytest.raises(AgentHumanInterruptException):
            raise_hitl_interrupt("req-1", "waiting")

    def test_suppressed_in_docker(self, monkeypatch):
        monkeypatch.setattr(settings, "EXECUTION_MODE", "docker")
        assert raise_hitl_interrupt("req-1", "waiting") is None


class TestAskHumanDockerAuto:
    @pytest.mark.asyncio
    async def test_docker_text_returns_empty_without_creating_request(
        self, monkeypatch
    ):
        monkeypatch.setattr(settings, "EXECUTION_MODE", "docker")
        with patch("app.core.hitl.tools.create_request", AsyncMock()) as mock_create:
            result = await ask_human(prompt="请提供信息")
        assert result == ""
        mock_create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_docker_confirmation_returns_approved(self, monkeypatch):
        monkeypatch.setattr(settings, "EXECUTION_MODE", "docker")
        with patch("app.core.hitl.tools.create_request", AsyncMock()) as mock_create:
            result = await ask_human(prompt="确认继续？", input_type="confirmation")
        assert result == "APPROVED"
        mock_create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_docker_uses_default(self, monkeypatch):
        monkeypatch.setattr(settings, "EXECUTION_MODE", "docker")
        result = await ask_human(
            prompt="选择", input_type="choice", default_value="skip"
        )
        assert result == "skip"


class TestAskConfirmDockerAuto:
    @pytest.mark.asyncio
    async def test_docker_single_auto_approved(self, monkeypatch):
        monkeypatch.setattr(settings, "EXECUTION_MODE", "docker")
        with patch.object(HITLOrchestrator, "raise_approval", AsyncMock()) as mock_raise:
            result = await ask_confirm(action_description="删除目录")
        assert result == "APPROVED"
        mock_raise.assert_not_awaited()


class _FakeMacro:
    name = "fmt-macro"
    id = 1
    risk_tier = "high"
    requires_confirmation = True
    project_id = None


def _macro_run_result(*, success=True, message="ok"):
    return SimpleNamespace(
        status="completed" if success else "failed",
        success=success,
        message=message,
        step_log=[],
        extracted_data=None,
    )


class TestRunMacroDockerConfirmation:
    @pytest.mark.asyncio
    async def test_docker_skips_confirmation_and_executes(self, monkeypatch):
        monkeypatch.setattr(settings, "EXECUTION_MODE", "docker")
        with (
            patch.object(
                run_macro_mod, "load_macro", AsyncMock(return_value=_FakeMacro())
            ),
            patch.object(
                run_macro_mod,
                "find_macro_by_name",
                AsyncMock(return_value=_FakeMacro()),
            ),
            patch.object(
                run_macro_mod, "_request_macro_confirmation", AsyncMock()
            ) as mock_confirm,
            patch.object(
                run_macro_mod, "resolve_project_base_url", AsyncMock(return_value=None)
            ),
            patch.object(
                run_macro_mod.MacroEngine,
                "run",
                AsyncMock(return_value=_macro_run_result()),
            ),
        ):
            result = await run_macro_mod._run_macro_row(
            None, "fmt-macro", None, "t-1"
        )
        assert "执行完成" in result
        mock_confirm.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_local_requests_confirmation(self, monkeypatch):
        monkeypatch.setattr(settings, "EXECUTION_MODE", "local")
        cfg = {"configurable": {"thread_id": "t-1"}}
        with (
            patch.object(
                run_macro_mod, "load_macro", AsyncMock(return_value=_FakeMacro())
            ),
            patch.object(
                run_macro_mod,
                "find_macro_by_name",
                AsyncMock(return_value=_FakeMacro()),
            ),
            patch.object(
                run_macro_mod, "_request_macro_confirmation", AsyncMock()
            ) as mock_confirm,
            patch(
                "app.core.hitl.authorization.AuthorizationService.is_granted",
                AsyncMock(return_value=False),
            ),
            patch(
                "app.core.hitl.core.find_recently_approved_by_key",
                AsyncMock(return_value=None),
            ),
        ):
            await run_macro_mod._run_macro_row(None, "fmt-macro", None, "t-1")
        mock_confirm.assert_awaited_once()
