"""Unit tests for run_macro result formatting and permanent-grant bypass.

Covers the two run_macro behaviors added in the uncommitted changes:
1. _format_macro_result — structured step-level summary that lets the Agent
   tell whether a macro really took effect (not just "completed").
2. Permanent-grant bypass in _run_macro_row — a persistent ``GrantedPermission``
   (grant_mode=always → ``AuthorizationService.is_granted``) skips the per-call
   HITL confirmation; otherwise confirmation still applies.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.engine.tools.react_macro import _format_macro_result, _run_macro_row


def _fake_macro(requires_confirmation: bool = True) -> MagicMock:
    macro = MagicMock()
    macro.id = 979
    macro.name = "改余额{query}"
    macro.risk_tier = "money"
    macro.project_id = 120
    macro.requires_confirmation = requires_confirmation
    return macro


def _result(step_log=None, extracted_data=None, **overrides):
    r = MagicMock()
    r.step_log = step_log
    r.extracted_data = extracted_data
    r.status = overrides.pop("status", "ok")
    r.success = overrides.pop("success", True)
    r.message = overrides.pop("message", "done")
    for k, v in overrides.items():
        setattr(r, k, v)
    return r


class TestFormatMacroResult:
    def test_empty_when_no_log_and_no_data(self):
        assert _format_macro_result(_fake_macro(), _result(step_log=[], extracted_data=None)) is None

    def test_success_summary_with_step_log(self):
        macro = _fake_macro()
        result = _result(
            step_log=[
                {"step": 1, "event_type": "navigate", "ok": True},
                {"step": 2, "event_type": "extract", "key": "title", "ok": True},
            ],
            extracted_data={"title": "iPhone"},
        )
        text = _format_macro_result(macro, result)
        assert text is not None
        assert "步骤 2/2 通过" in text
        assert "步骤明细" in text
        assert "1:navigate" in text
        assert "2:extract" in text
        assert "提取数据" in text
        assert "iPhone" in text

    def test_failure_summary_reports_failed_steps(self):
        result = _result(
            success=False,
            message="step 2 failed",
            step_log=[
                {"step": 1, "event_type": "navigate", "ok": True},
                {"step": 2, "event_type": "click", "ok": False, "error": "element not found"},
            ],
            extracted_data=None,
        )
        text = _format_macro_result(_fake_macro(), result)
        assert "步骤 1/2 通过" in text
        assert "未生效步骤" in text
        assert "element not found" in text

    def test_failure_step_without_error_uses_fallback(self):
        result = _result(
            step_log=[{"step": 3, "event_type": "run_js", "ok": False}],
            extracted_data=None,
        )
        text = _format_macro_result(_fake_macro(), result)
        assert "未生效" in text

    def test_extracted_data_is_json_serialized(self):
        result = _result(step_log=None, extracted_data={"items": [1, 2], "note": "中文"})
        text = _format_macro_result(_fake_macro(), result)
        assert "提取数据" in text
        assert "中文" in text


class TestPermanentGrantBypass:
    @pytest.mark.asyncio
    async def test_permanent_grant_bypasses_confirmation(self):
        """requires_confirmation 宏命中未过期的持久化授权 → 跳过确认直接执行。"""
        macro = _fake_macro()

        with patch(
            "app.core.engine.tools.react_macro.load_macro",
            AsyncMock(return_value=macro),
        ), patch(
            "app.core.hitl.authorization.AuthorizationService.is_granted",
            AsyncMock(return_value=True),
        ) as mock_granted, patch(
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

            result = await _run_macro_row(979, None, {"query": "u1"}, "thread-1")

        mock_granted.assert_awaited_once()
        mock_engine.assert_awaited_once()
        assert "改余额" in result

    @pytest.mark.asyncio
    async def test_permanent_grant_matches_macro_path_and_action(self):
        """永久授权判定必须按宏粒度路径（macro:{id}）与 macro_run 动作查询。"""
        macro = _fake_macro()

        with patch(
            "app.core.engine.tools.react_macro.load_macro",
            AsyncMock(return_value=macro),
        ), patch(
            "app.core.hitl.authorization.AuthorizationService.is_granted",
            AsyncMock(return_value=True),
        ) as mock_granted, patch(
            "app.core.engine.tools.react_macro.resolve_project_base_url",
            AsyncMock(return_value="http://127.0.0.1:9003"),
        ), patch(
            "app.core.engine.tools.react_macro.MacroEngine.run",
            AsyncMock(
                return_value=MagicMock(
                    status="ok", success=True, message="done", extracted_data=None
                )
            ),
        ):

            await _run_macro_row(979, None, {"query": "u1", "new_stock": 555}, "thread-1")

        args = mock_granted.await_args.args
        assert args == ("macro:979", "macro_run")

    @pytest.mark.asyncio
    async def test_permanent_grant_not_covered_falls_back_to_hitl(self):
        """永久授权未覆盖 → 仍走 HITL 确认（不直接执行）。"""
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
            "app.core.hitl.authorization.AuthorizationService.is_granted",
            AsyncMock(return_value=False),
        ), patch(
            "app.core.hitl.core._find_pending_by_key",
            AsyncMock(return_value=None),
        ), patch(
            "app.core.hitl.core.find_recently_approved_by_key",
            AsyncMock(return_value=None),
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
        mock_engine.assert_not_awaited()


class InterruptSentinel(Exception):
    """Sentinel exception to simulate raise_hitl_interrupt."""
