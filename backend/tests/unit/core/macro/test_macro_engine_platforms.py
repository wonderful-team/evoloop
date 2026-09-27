"""Coverage for platform executors (desktop/mobile), dump MCP/webhook sinks and
condition evaluation."""

from types import SimpleNamespace
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
    from app.core.learning.macro.engine import activity_monitor

    monkeypatch.setattr(activity_monitor, "check_cancellation", AsyncMock())
    monkeypatch.setattr(activity_monitor, "log_event", AsyncMock())


def _step(event_type, source, step_number=1, **payload):
    return MacroStep(
        type=MacroStepType.ACTION,
        event_type=event_type,
        source=source,
        step_number=step_number,
        payload=payload,
    )


class TestDesktopExecutor:
    @pytest.mark.asyncio
    async def test_applescript(self, monkeypatch):
        from app.core.environment.controllers.desktop import DesktopController

        monkeypatch.setattr(DesktopController, "execute", AsyncMock(return_value="OK"))
        ok, msg, _ = await MacroEngine.execute(
            "t",
            MacroScript(
                steps=[
                    _step("applescript", MacroSource.DESKTOP, script="tell app ...")
                ]
            ),
            skip_activity_log=True,
        )
        assert ok is True


class TestMobileExecutor:
    @pytest.mark.asyncio
    async def test_tap(self, monkeypatch):
        from app.core.environment.controllers.mobile import MobileController

        monkeypatch.setattr(MobileController, "execute", AsyncMock(return_value="OK"))
        ok, msg, _ = await MacroEngine.execute(
            "t",
            MacroScript(steps=[_step("tap", MacroSource.MOBILE, x=10, y=20)]),
            skip_activity_log=True,
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_swipe(self, monkeypatch):
        from app.core.environment.controllers.mobile import MobileController

        mock = AsyncMock(return_value="OK")
        monkeypatch.setattr(MobileController, "execute", mock)
        ok, msg, _ = await MacroEngine.execute(
            "t",
            MacroScript(
                steps=[
                    _step(
                        "swipe",
                        MacroSource.MOBILE,
                        x=1, y=2, end_x=50, end_y=60, duration_ms=200,
                    )
                ]
            ),
            skip_activity_log=True,
        )
        assert ok is True
        mock.assert_awaited()


class TestDumpWebhook:
    @pytest.mark.asyncio
    async def test_webhook_post(self, monkeypatch):
        from app.core.learning.macro.engine import DumpMixin

        fake_post = AsyncMock()
        fake_client = AsyncMock()
        fake_client.post = fake_post
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)

        monkeypatch.setattr("httpx.AsyncClient", lambda **kw: fake_client)
        await DumpMixin._dump_to_webhook(
            "t",
            {"webhook_url": "https://x.com/h", "method": "POST"},
            {"a": 1},
        )
        fake_post.assert_awaited()


class TestDumpMCP:
    @pytest.mark.asyncio
    async def test_mcp_dump(self, monkeypatch):
        from app.core.learning.macro.engine import DumpMixin

        target = SimpleNamespace(
            name="mcp__supabase__upsert",
            ainvoke=AsyncMock(return_value={"ok": True}),
        )
        monkeypatch.setattr(
            "app.core.mcp.mcp_client_manager.get_tools",
            AsyncMock(return_value=[target]),
        )
        await DumpMixin._dump_to_mcp(
            "t",
            {"mcp_server": "supabase", "mcp_tool": "upsert", "table": "data"},
            {"a": 1},
        )
        target.ainvoke.assert_awaited()


class TestEvaluateCondition:
    @pytest.mark.asyncio
    async def test_element_exists_dom(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController
        from app.core.learning.macro.engine import ControlMixin

        monkeypatch.setattr(
            BrowserController, "execute", AsyncMock(return_value="Found element")
        )
        result = await ControlMixin._evaluate_condition(
            "element_exists", "#x", MacroSource.DOM
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_element_exists_desktop_true(self, monkeypatch):
        from app.core.environment.controllers.desktop import DesktopController
        from app.core.learning.macro.engine import ControlMixin

        monkeypatch.setattr(
            DesktopController, "execute", AsyncMock(return_value="true")
        )
        result = await ControlMixin._evaluate_condition(
            "element_exists", "Button 1", MacroSource.DESKTOP
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_unknown_condition_returns_none(self, monkeypatch):
        from app.core.learning.macro.engine import ControlMixin

        assert (
            await ControlMixin._evaluate_condition("bogus", "#x", MacroSource.DOM)
            is False
        )


DESKTOP_ACTIONS = [
    ("ax_press", {"bundle_id": "com.x", "ax_action": "press", "role": "AXButton", "label": "OK"}),
    ("ax_menu_press", {"bundle_id": "com.x", "menu_labels": ["File"]}),
    ("ax_set_value", {"bundle_id": "com.x", "role": "AXTextField", "label": "Name", "value": "v"}),
    ("cgclick", {"x": 10, "y": 20}),
    ("drag_drop", {"x": 1, "y": 2, "x2": 3, "y2": 4, "source_element": "a", "target_element": "b"}),
    ("dump_ui", {}),
    ("get_active_app", {}),
    ("get_info", {}),
    ("open_app", {"package_name": "com.x"}),
    ("screenshot", {"path": "/tmp/s.png"}),
    ("wait", {"duration_ms": 1}),
    ("double_click", {"x": 10, "y": 20}),
]

MOBILE_ACTIONS = [
    ("back_key", {}),
    ("home", {}),
    ("long_press", {"x": 10, "y": 20}),
    ("open_app", {"package_name": "com.x"}),
    ("screenshot", {"path": "/tmp/s.png"}),
    ("scroll", {"direction": "down"}),
    ("double_click", {"x": 10, "y": 20}),
    ("dump_ui", {}),
    ("wait", {"duration_ms": 1}),
]


@pytest.fixture
def mock_ax(monkeypatch):
    import app.core.atlas.ax_actions as ax

    monkeypatch.setattr(ax, "ensure_pid", lambda *a: 1)
    monkeypatch.setattr(ax, "perform_by_label", lambda *a: True)
    monkeypatch.setattr(ax, "press_at_path", lambda *a: True)
    monkeypatch.setattr(ax, "press_menu_labels", lambda *a: True)
    monkeypatch.setattr(ax, "set_value_by_label", lambda *a: True)
    monkeypatch.setattr(ax, "set_value_at_path", lambda *a: True)


class TestDesktopAllActions:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("event_type,payload", DESKTOP_ACTIONS)
    async def test_desktop_action(self, monkeypatch, mock_ax, event_type, payload):
        from app.core.environment.controllers.desktop import DesktopController

        monkeypatch.setattr(DesktopController, "execute", AsyncMock(return_value="OK"))
        ok, msg, _ = await MacroEngine.execute(
            "t",
            MacroScript(steps=[_step(event_type, MacroSource.DESKTOP, **payload)]),
            skip_activity_log=True,
        )
        assert ok is True


class TestMobileAllActions:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("event_type,payload", MOBILE_ACTIONS)
    async def test_mobile_action(self, monkeypatch, event_type, payload):
        from app.core.environment.controllers.mobile import MobileController

        monkeypatch.setattr(MobileController, "execute", AsyncMock(return_value="OK"))
        ok, msg, _ = await MacroEngine.execute(
            "t",
            MacroScript(steps=[_step(event_type, MacroSource.MOBILE, **payload)]),
            skip_activity_log=True,
        )
        assert ok is True
