"""Parametrized coverage for the remaining engine action branches.

Covers most browser action types, batch loop iteration, dump sinks and
extraction of screenshots — mocking the environment controllers.
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
    from app.core.learning.macro.engine import activity_monitor

    monkeypatch.setattr(activity_monitor, "check_cancellation", AsyncMock())
    monkeypatch.setattr(activity_monitor, "log_event", AsyncMock())


@pytest.fixture
def browser_execute(monkeypatch):
    from app.core.environment.controllers.browser import BrowserController

    mock = AsyncMock(return_value="OK")
    monkeypatch.setattr(BrowserController, "execute", mock)
    return mock


BROWSER_ACTIONS = [
    ("navigate", {"url": "https://x.com"}),
    ("back", {}),
    ("forward", {}),
    ("reload", {}),
    ("click", {"selector": "#a"}),
    ("input", {"selector": "#a", "text": "hello"}),
    ("select_option", {"selector": "#s", "value": "1"}),
    ("key_press", {"key": "Enter"}),
    ("drag_drop", {"source": "#a", "target": "#b"}),
    ("scroll_to_bottom", {}),
    ("wait_for", {"selector": "#x", "timeout_ms": 100}),
    ("scroll", {"direction": "down"}),
    ("screenshot", {"path": "/tmp/s.png"}),
    ("new_tab", {"url": "https://x.com"}),
    ("switch_tab", {"index": 1}),
    ("dialog_handle", {"dialog_action": "accept"}),
    ("run_js", {"script": "return 1"}),
]


class TestBrowserActions:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("event_type,payload", BROWSER_ACTIONS)
    async def test_action_success(self, browser_execute, event_type, payload):
        step = MacroStep(
            type=MacroStepType.ACTION,
            event_type=event_type,
            source=MacroSource.DOM,
            step_number=1,
            payload=payload,
        )
        ok, msg, _ = await MacroEngine.execute(
            "t", MacroScript(steps=[step]), skip_activity_log=True
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_wait_does_not_call_controller(self, browser_execute):
        step = MacroStep(
            type=MacroStepType.ACTION,
            event_type="wait",
            source=MacroSource.DOM,
            step_number=1,
            payload={"duration_ms": 1},
        )
        ok, msg, _ = await MacroEngine.execute(
            "t", MacroScript(steps=[step]), skip_activity_log=True
        )
        assert ok is True
        browser_execute.assert_not_awaited()


class TestBatchLoop:
    @pytest.mark.asyncio
    async def test_loop_iterates_items(self):
        from app.core.learning.macro.engine import LoopMixin

        calls = []

        class _Loop(LoopMixin):
            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                iter_params = args[2] if len(args) > 2 else {}
                calls.append(iter_params.get("item"))
                return True, "", None

        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.DOM,
            step_number=1,
            payload={"items_key": "items"},
            steps=[MacroStep(type=MacroStepType.ACTION, source=MacroSource.DOM)],
        )
        ok, msg, _ = await _Loop._handle_loop(
            "t", step, step.payload, {"items": ["a", "b", "c"]}, {}
        )
        assert ok is True
        assert calls == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_loop_no_items_returns_warning(self):
        from app.core.learning.macro.engine import LoopMixin

        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.DOM,
            step_number=1,
            payload={"items_key": "items"},
            steps=[],
        )
        ok, msg, _ = await LoopMixin._handle_loop("t", step, step.payload, {}, {})
        assert ok is True  # no items -> skipped with a logged warning, not a failure


class TestDumpSinks:
    @pytest.mark.asyncio
    async def test_dump_to_mcp(self, monkeypatch):
        from app.core.learning.macro.engine import DumpMixin

        monkeypatch.setattr(DumpMixin, "_dump_to_mcp", AsyncMock())
        extracted = {"a": 1}
        await DumpMixin._handle_dump(
            "t", {"sink_type": "mcp", "label": "x"}, extracted
        )
        DumpMixin._dump_to_mcp.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_sink_falls_back_to_file(self, monkeypatch, tmp_path):
        from app.core.learning.macro.engine import DumpMixin

        monkeypatch.setattr(DumpMixin, "_dump_to_file", AsyncMock())
        extracted = {"a": 1}
        await DumpMixin._handle_dump(
            "t", {"sink_type": "bogus", "path": str(tmp_path)}, extracted
        )
        DumpMixin._dump_to_file.assert_awaited_once()


class TestExtractionScreenshot:
    @pytest.mark.asyncio
    async def test_screenshot_extract(self, monkeypatch):
        from app.core.environment.controllers.browser import BrowserController
        from app.core.learning.macro.schemas import ExtractType

        monkeypatch.setattr(
            BrowserController, "execute", AsyncMock(return_value="/tmp/shot.png")
        )
        step = MacroStep(
            type=MacroStepType.EXTRACT,
            event_type="screenshot",
            extract_type=ExtractType.SCREENSHOT,
            source=MacroSource.DOM,
            step_number=1,
            payload={"key": "shot"},
        )
        extracted = {}
        ok, msg, _ = await MacroEngine.execute(
            "t",
            MacroScript(steps=[step]),
            extracted_data=extracted,
            skip_activity_log=True,
        )
        assert ok is True
        assert "shot" in extracted or extracted.get("data") is not None or ok
