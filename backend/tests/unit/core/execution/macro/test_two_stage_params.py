"""MacroEngine two-stage param feedback: extracted values feed later steps."""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.core.execution.macro.engine import MacroEngine
from app.core.execution.macro.schemas import MacroScript


def _script(steps: list[dict]) -> MacroScript:
    return MacroScript(steps=steps)


class TestExtractedDataFeedback:
    async def test_extracted_value_resolves_downstream_placeholder(self, monkeypatch):
        navigated: list[str] = []
        monkeypatch.setattr(
            MacroEngine,
            "_handle_extraction",
            AsyncMock(side_effect=lambda *a: a[5].__setitem__("entity_id", "42")),
        )

        async def fake_browser_step(event_type, _selector, payload):
            if event_type == "navigate":
                navigated.append(payload["url"])

        monkeypatch.setattr(
            MacroEngine,
            "_execute_browser_step",
            AsyncMock(side_effect=fake_browser_step),
        )
        monkeypatch.setattr(
            "app.core.monitoring.activity.activity_monitor.log_event",
            AsyncMock(return_value=None),
        )

        script = _script(
            [
                {
                    "step_number": 1,
                    "type": "extract",
                    "event_type": "get_attribute",
                    "source": "dom",
                    "target_selector": "[data-goods-id]",
                    "extract_type": "get_attribute",
                    "key": "entity_id",
                    "payload": {"attribute": "data-goods-id"},
                },
                {
                    "step_number": 2,
                    "type": "action",
                    "event_type": "navigate",
                    "source": "dom",
                    "payload": {
                        "url": "http://x/shop/goods/editgoods?id={{entity_id}}"
                    },
                },
            ]
        )
        ok, msg, _ = await MacroEngine.execute("t-2stage", script, params={})
        assert ok, msg
        assert navigated == ["http://x/shop/goods/editgoods?id=42"]

    async def test_unresolved_placeholder_fails_navigate_loudly(self, monkeypatch):
        monkeypatch.setattr(
            MacroEngine,
            "_handle_extraction",
            AsyncMock(side_effect=lambda *a: a[5].__setitem__("entity_id", None)),
        )
        monkeypatch.setattr(
            MacroEngine, "_execute_browser_step", AsyncMock(return_value=None)
        )
        monkeypatch.setattr(
            "app.core.monitoring.activity.activity_monitor.log_event",
            AsyncMock(return_value=None),
        )

        script = _script(
            [
                {
                    "step_number": 1,
                    "type": "extract",
                    "event_type": "get_attribute",
                    "source": "dom",
                    "target_selector": "[data-goods-id]",
                    "extract_type": "get_attribute",
                    "key": "entity_id",
                    "payload": {"attribute": "data-goods-id"},
                },
                {
                    "step_number": 2,
                    "type": "action",
                    "event_type": "navigate",
                    "source": "dom",
                    "payload": {"url": "http://x/edit?id={{entity_id}}"},
                },
            ]
        )
        ok, msg, _ = await MacroEngine.execute("t-unresolved", script, params={})
        assert not ok
        assert "未解析" in msg

    async def test_caller_params_win_over_extracted(self, monkeypatch):
        navigated: list[str] = []
        monkeypatch.setattr(
            MacroEngine,
            "_handle_extraction",
            AsyncMock(side_effect=lambda *a: a[5].__setitem__("entity_id", "42")),
        )

        async def fake_browser_step(event_type, _selector, payload):
            if event_type == "navigate":
                navigated.append(payload["url"])

        monkeypatch.setattr(
            MacroEngine,
            "_execute_browser_step",
            AsyncMock(side_effect=fake_browser_step),
        )
        monkeypatch.setattr(
            "app.core.monitoring.activity.activity_monitor.log_event",
            AsyncMock(return_value=None),
        )

        script = _script(
            [
                {
                    "step_number": 1,
                    "type": "extract",
                    "event_type": "get_attribute",
                    "source": "dom",
                    "target_selector": "[data-goods-id]",
                    "extract_type": "get_attribute",
                    "key": "entity_id",
                    "payload": {"attribute": "data-goods-id"},
                },
                {
                    "step_number": 2,
                    "type": "action",
                    "event_type": "navigate",
                    "source": "dom",
                    "payload": {"url": "http://x/edit?id={{entity_id}}"},
                },
            ]
        )
        ok, _, _ = await MacroEngine.execute(
            "t-precedence", script, params={"entity_id": "7"}
        )
        assert ok
        assert navigated == ["http://x/edit?id=7"]
