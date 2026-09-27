"""单元测试：create_macro dry-run 验证链路修复。

覆盖三个回归点（测试人员实验暴露的系统缺陷）：
1. verify_macro_script 注入 {{base_url}}（dry-run 与真实执行对齐）
2. verify_macro_script 失败时把真实错误（message）传达给 Agent
3. navigate 相对路径守卫：给出可行动的 {{base_url}} 提示而非
   "Cannot navigate to invalid URL"
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.learning.macro.engine import MacroEngine
from app.core.learning.macro.schemas import (
    MacroScript,
    MacroSource,
    MacroStep,
    MacroStepType,
)
from app.core.learning.macro.utils import verify_macro_script


@pytest.fixture(autouse=True)
def _mock_activity(monkeypatch):
    from app.core.learning.macro.engine import activity_monitor

    async def no_cancel(*args, **kwargs):  # noqa: ARG001
        return None

    monkeypatch.setattr(activity_monitor, "check_cancellation", no_cancel)


def _step(event_type="click", source=MacroSource.DOM, step_number=1, **payload) -> MacroStep:
    return MacroStep(
        type=MacroStepType.ACTION,
        event_type=event_type,
        source=source,
        step_number=step_number,
        payload=payload,
    )


def _script(*steps) -> MacroScript:
    return MacroScript(steps=list(steps))


class TestVerifyMacroScriptBaseUrlInjection:
    """修复 1：dry-run 验证注入 {{base_url}}，否则 navigate 必败。"""

    @pytest.mark.asyncio
    async def test_injects_base_url_from_project(self):
        with patch(
            "app.core.learning.macro.runner.resolve_project_base_url",
            new=AsyncMock(return_value="http://localhost:8081"),
        ), patch(
            "app.core.learning.macro.utils.MacroService.run",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "extracted_data": {},
                    "message": "ok",
                }
            ),
        ) as mock_run:
            await verify_macro_script(
                [{"type": "extract", "key": "x"}],
                thread_id="t",
                _project_id=120,
            )
        params = mock_run.call_args.kwargs["params"]
        assert params["base_url"] == "http://localhost:8081"

    @pytest.mark.asyncio
    async def test_no_project_skips_injection(self):
        with patch(
            "app.core.learning.macro.utils.MacroService.run",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "extracted_data": {},
                    "message": "ok",
                }
            ),
        ) as mock_run:
            await verify_macro_script(
                [{"type": "extract", "key": "x"}], thread_id="t"
            )
        params = mock_run.call_args.kwargs["params"]
        assert "base_url" not in params

    @pytest.mark.asyncio
    async def test_explicit_params_base_url_wins(self):
        with patch(
            "app.core.learning.macro.utils.MacroService.run",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "extracted_data": {},
                    "message": "ok",
                }
            ),
        ) as mock_run:
            await verify_macro_script(
                [{"type": "extract", "key": "x"}],
                thread_id="t",
                _project_id=120,
                params={"base_url": "http://custom:9000"},
            )
        params = mock_run.call_args.kwargs["params"]
        assert params["base_url"] == "http://custom:9000"


class TestVerifyMacroScriptErrorDetail:
    """修复 2：失败时把真实错误（MacroRunResult.message）传达给 Agent。"""

    @pytest.mark.asyncio
    async def test_error_falls_back_to_message(self):
        with patch(
            "app.core.learning.macro.utils.MacroService.run",
            new=AsyncMock(
                return_value={
                    "success": False,
                    "message": "Cannot navigate to invalid URL",
                    "extracted_data": {},
                }
            ),
        ):
            result = await verify_macro_script(
                [{"type": "extract", "key": "x"}], thread_id="t"
            )
        assert result.success is False
        assert result.error is not None
        assert "Cannot navigate" in result.error

    @pytest.mark.asyncio
    async def test_error_field_has_priority(self):
        with patch(
            "app.core.learning.macro.utils.MacroService.run",
            new=AsyncMock(
                return_value={
                    "success": False,
                    "error": "step 1 failed",
                    "message": "Cannot navigate to invalid URL",
                    "extracted_data": {},
                }
            ),
        ):
            result = await verify_macro_script(
                [{"type": "extract", "key": "x"}], thread_id="t"
            )
        assert result.error == "step 1 failed"

    @pytest.mark.asyncio
    async def test_success_has_no_error(self):
        with patch(
            "app.core.learning.macro.utils.MacroService.run",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "message": "ok",
                    "extracted_data": {"x": 1},
                }
            ),
        ):
            result = await verify_macro_script(
                [{"type": "extract", "key": "x"}], thread_id="t"
            )
        assert result.success is True
        assert result.error is None


class TestNavigateUrlGuard:
    """修复 3：navigate 相对路径在进浏览器前拦截，给出 {{base_url}} 提示。"""

    @pytest.mark.asyncio
    async def test_relative_url_rejected_with_hint(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController

        mock_exec = AsyncMock()
        monkeypatch.setattr(BrowserController, "execute", mock_exec)
        ok, msg, ctx = await MacroEngine.execute(
            "t",
            _script(
                _step(
                    event_type="navigate",
                    url="/shop.html#url=shop/goods/lists",
                )
            ),
            skip_activity_log=True,
        )
        assert ok is False
        assert "{{base_url}}" in msg
        assert "绝对 URL" in msg
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_absolute_url_passes_guard(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController

        monkeypatch.setattr(
            BrowserController, "execute", AsyncMock(return_value="OK")
        )
        ok, msg, _ = await MacroEngine.execute(
            "t",
            _script(
                _step(
                    event_type="navigate",
                    url="http://localhost:8081/shop.html#url=shop/goods/lists",
                )
            ),
            skip_activity_log=True,
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_placeholder_url_blocked_with_hint(self, monkeypatch):
        """占位符未注入（无 base_url 参数）时报「未解析 URL」而非 invalid URL。"""
        from app.core.environment.controllers.browser import BrowserController

        mock_exec = AsyncMock()
        monkeypatch.setattr(BrowserController, "execute", mock_exec)
        ok, msg, _ = await MacroEngine.execute(
            "t",
            _script(
                _step(
                    event_type="navigate",
                    url="{{base_url}}/shop.html#url=shop/goods/lists",
                )
            ),
            skip_activity_log=True,
        )
        assert ok is False
        assert "base_url" in msg
        mock_exec.assert_not_called()

class TestCollectLoopWarningsPropagation:
    """_handle_collect_loop 必须把 execution_warnings 传递给子步骤执行
    （此前签名缺参 → NameError: execution_warnings is not defined）。"""

    @pytest.mark.asyncio
    async def test_collect_loop_forwards_warnings_to_execute_steps(
        self, tmp_path, monkeypatch
    ):
        import json

        from app.core.learning.macro.engine import LoopMixin
        from app.core.learning.macro.schemas import MacroStep, MacroStepType

        state_file = tmp_path / "collect.json"
        state_file.write_text(
            json.dumps(
                {
                    "items": [
                        {"signature": "s1", "status": "pending", "tap_x": 1, "tap_y": 2},
                    ],
                    "phase": "detail",
                }
            )
        )

        received = {}

        class _Loop(LoopMixin):
            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                received["warnings"] = kwargs.get("execution_warnings")
                return True, "", None

        monkeypatch.setattr(
            "app.core.environment.controllers.mobile.MobileController.execute",
            AsyncMock(return_value="OK"),
        )
        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.MOBILE,
            step_number=1,
            steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.MOBILE)],
        )
        warnings = []
        ok, msg, _ = await _Loop._handle_collect_loop(
            "t",
            step,
            {
                "state_file": str(state_file),
                "detail_config": {"limit": 10, "wait_after_tap_ms": 1},
            },
            {},
            {},
            disable_ocr=True,
            collect_mode="detail",
            execution_warnings=warnings,
        )
        assert ok is True
        assert received.get("warnings") is warnings

    @pytest.mark.asyncio
    async def test_control_loop_dispatch_passes_warnings(self, monkeypatch):
        """_handle_control_flow 的 collect 分支必须把 warnings 传给
        _handle_collect_loop（此前漏传导致 warnings 丢失/NameError）。"""
        import json


        state_file = "/tmp/macro_collect_dispatch_test.json"
        with open(state_file, "w") as f:
            json.dump(
                {
                    "items": [
                        {"signature": "s1", "status": "pending", "tap_x": 1, "tap_y": 2},
                    ],
                    "phase": "detail",
                },
                f,
            )
        monkeypatch.setattr(
            "app.core.environment.controllers.mobile.MobileController.execute",
            AsyncMock(return_value="OK"),
        )

        from app.core.learning.macro.engine import ControlMixin, LoopMixin

        calls = {}

        class _Loop(ControlMixin, LoopMixin):
            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                calls["warnings"] = kwargs.get("execution_warnings")
                return True, "", None

        from app.core.learning.macro.schemas import MacroStep, MacroStepType

        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.MOBILE,
            step_number=1,
            collect_mode="detail",
            payload={"state_file": state_file, "detail_config": {"limit": 1, "wait_after_tap_ms": 1}},
            steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.MOBILE)],
        )
        warnings = []
        ok, msg, _ = await _Loop._handle_control_flow(
            "t",
            step,
            step.payload,
            {},
            {},
            disable_ocr=True,
            execution_warnings=warnings,
        )
        assert ok is True
        assert calls.get("warnings") is warnings
