"""Coverage for the macro engine action executors (browser/desktop/mobile steps).

Mocks the environment controllers so the engine's dispatch, error handling and
retry semantics can be exercised without a real browser/phone.
"""

from unittest.mock import AsyncMock

import pytest

from app.core.learning.macro.engine import MacroEngine
from app.core.learning.macro.schemas import (
    MacroScript,
    MacroSource,
    MacroStep,
    MacroStepType,
)


@pytest.fixture(autouse=True)
def _mock_activity(monkeypatch):
    """The engine calls check_cancellation each step (DB-backed) — no-op it."""
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


class TestBrowserExecutor:
    @pytest.mark.asyncio
    async def test_click_success(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController

        monkeypatch.setattr(
            BrowserController, "execute", AsyncMock(return_value="OK")
        )
        ok, msg, _ = await MacroEngine.execute(
            "t", _script(_step(event_type="click", selector="#btn")), skip_activity_log=True
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_verify_assertion_matches(self, monkeypatch):
        """VERIFY 返回的状态匹配 expect → 宏成功。"""
        from app.core.environment.controllers.browser import BrowserController

        monkeypatch.setattr(
            BrowserController, "execute", AsyncMock(return_value="JS result: VERIFY:待转账")
        )
        ok, msg, _ = await MacroEngine.execute(
            "t",
            _script(_step(event_type="run_js", script="()=>'VERIFY:x'", expect="待转账|买家待退货")),
            skip_activity_log=True,
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_verify_assertion_fails(self, monkeypatch):
        """VERIFY 返回的状态不匹配 expect（如售后仍"申请售后"）→ 宏失败。"""
        from app.core.environment.controllers.browser import BrowserController

        monkeypatch.setattr(
            BrowserController, "execute", AsyncMock(return_value="JS result: VERIFY:申请售后")
        )
        ok, msg, _ = await MacroEngine.execute(
            "t",
            _script(_step(event_type="run_js", script="()=>'VERIFY:x'", expect="待转账|买家待退货")),
            skip_activity_log=True,
        )
        assert ok is False
        assert "VERIFY assertion failed" in msg

    @pytest.mark.asyncio
    async def test_verify_no_expect_passthrough(self, monkeypatch):
        """未声明 expect 时 VERIFY 结果透传，不改变成败。"""
        from app.core.environment.controllers.browser import BrowserController

        monkeypatch.setattr(
            BrowserController, "execute", AsyncMock(return_value="JS result: VERIFY:申请售后")
        )
        ok, msg, _ = await MacroEngine.execute(
            "t",
            _script(_step(event_type="run_js", script="()=>'VERIFY:x'")),
            skip_activity_log=True,
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_input_success(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController

        mock = AsyncMock(return_value="OK")
        monkeypatch.setattr(BrowserController, "execute", mock)
        ok, msg, _ = await MacroEngine.execute(
            "t",
            _script(_step(event_type="input", selector="#name", text="hello")),
            skip_activity_log=True,
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_controller_failure_stops_macro(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController

        monkeypatch.setattr(
            BrowserController, "execute", AsyncMock(return_value="❌ Execution failed")
        )
        ok, msg, data = await MacroEngine.execute(
            "t", _script(_step(event_type="click", selector="#btn")), skip_activity_log=True
        )
        assert ok is False
        assert data is not None and data.get("step_number") == 1

    @pytest.mark.asyncio
    async def test_continue_on_error_skips_failure(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController

        monkeypatch.setattr(
            BrowserController, "execute", AsyncMock(return_value="❌ Execution failed")
        )
        ok, msg, _ = await MacroEngine.execute(
            "t",
            _script(_step(event_type="click", selector="#btn", continue_on_error=True)),
            skip_activity_log=True,
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_multi_step_partial_failure(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController

        async def fake_execute(action, **kw):  # noqa: ARG001
            if action == "click":
                return "❌ boom"
            return "OK"

        monkeypatch.setattr(BrowserController, "execute", fake_execute)
        ok, msg, _ = await MacroEngine.execute(
            "t",
            _script(
                _step(event_type="click", selector="#a", step_number=1),
                _step(event_type="input", selector="#b", text="x", step_number=2),
            ),
            skip_activity_log=True,
        )
        assert ok is False


class TestDesktopExecutor:
    @pytest.mark.asyncio
    async def test_desktop_click_success(self, monkeypatch):
        from app.core.environment.controllers.desktop import DesktopController

        monkeypatch.setattr(
            DesktopController, "execute", AsyncMock(return_value="OK")
        )
        ok, msg, _ = await MacroEngine.execute(
            "t",
            _script(_step(event_type="click", source=MacroSource.DESKTOP, x=10, y=20)),
            skip_activity_log=True,
        )
        assert ok is True
