"""Coverage for MacroService.run orchestration and the macro event publishers /
L0 matcher subscriber."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.learning.macro.schemas import HealingDecision
from app.core.learning.macro.service import MacroService


class TestMacroServiceRun:
    @pytest.mark.asyncio
    async def test_success(self):
        with (
            patch(
                "app.core.learning.macro.service.MacroEngine.execute_steps",
                new=AsyncMock(return_value=(True, "done", None)),
            ),
            patch(
                "app.core.learning.macro.service.activity_monitor.start_run",
                new=AsyncMock(),
            ),
            patch(
                "app.core.learning.macro.service.activity_monitor.end_run",
                new=AsyncMock(),
            ),
            patch(
                "app.core.learning.macro.service.activity_monitor.log_event",
                new=AsyncMock(),
            ),
        ):
            result = await MacroService.run(
                thread_id="t",
                script_input=[
                    {"type": "action", "event_type": "click", "payload": {"x": 1}}
                ],
                params={},
            )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_empty_script(self):
        with patch(
            "app.core.learning.macro.service.activity_monitor.start_run",
            new=AsyncMock(),
        ):
            result = await MacroService.run(thread_id="t", script_input=[], params={})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_failure_self_healing_allowed(self):
        with (
            patch(
                "app.core.learning.macro.service.MacroEngine.execute_steps",
                new=AsyncMock(return_value=(False, "step failed", {"failed_step": 1})),
            ),
            patch(
                "app.core.learning.macro.service.SelfHealingPolicy.check",
                return_value=HealingDecision(
                    allowed=True, reason="ok", source="allowed"
                ),
            ),
            patch(
                "app.core.learning.macro.service.activity_monitor.start_run",
                new=AsyncMock(),
            ),
            patch(
                "app.core.learning.macro.service.activity_monitor.end_run",
                new=AsyncMock(),
            ),
            patch(
                "app.core.learning.macro.service.publish_macro_execution_failed",
                new=AsyncMock(),
            ),
        ):
            result = await MacroService.run(
                thread_id="t",
                script_input=[
                    {"type": "action", "event_type": "click", "payload": {"x": 1}}
                ],
                params={},
            )
        assert result.success is False
        assert result.status == "fallback_required"

    @pytest.mark.asyncio
    async def test_failure_self_healing_disabled(self):
        with (
            patch(
                "app.core.learning.macro.service.MacroEngine.execute_steps",
                new=AsyncMock(return_value=(False, "step failed", {})),
            ),
            patch(
                "app.core.learning.macro.service.SelfHealingPolicy.check",
                return_value=HealingDecision(
                    allowed=False, reason="no", source="execution"
                ),
            ),
            patch(
                "app.core.learning.macro.service.activity_monitor.start_run",
                new=AsyncMock(),
            ),
            patch(
                "app.core.learning.macro.service.activity_monitor.end_run",
                new=AsyncMock(),
            ),
        ):
            result = await MacroService.run(
                thread_id="t",
                script_input=[
                    {"type": "action", "event_type": "click", "payload": {"x": 1}}
                ],
                params={},
            )
        assert result.success is False
        assert result.allow_self_healing is False


class TestPublishExecutionFailed:
    @pytest.mark.asyncio
    async def test_publishes_and_returns_event(self, monkeypatch):
        from app.core.events import system_bus
        from app.core.learning.macro.event.publishers import (
            publish_macro_execution_failed,
        )

        sent = []

        async def fake_publish(event):
            sent.append(event)

        monkeypatch.setattr(system_bus, "publish", fake_publish)
        event = await publish_macro_execution_failed(
            macro_id=1,
            macro_name="m",
            error_message="boom",
            fallback_context={},
            thread_id="t",
        )
        assert len(sent) == 1
        assert event.macro_name == "m"


class TestL0MatcherSubscriber:
    @pytest.mark.asyncio
    async def test_lifecycle_invalidates_caches(self, monkeypatch):
        import app.core.learning.macro.event.subscribers as subs
        from app.core.learning.macro.event.subscribers import MacroL0MatcherSubscriber
        from app.core.routing.matcher_cache import matcher_cache

        monkeypatch.setattr(subs, "invalidate_macro_cache", lambda *a: None)
        monkeypatch.setattr(
            matcher_cache, "invalidate_and_schedule_rebuild", AsyncMock()
        )

        class _Event:
            macro_id = 42
            event_type = "macro_updated"
            data = {"macro_id": 42}

        sub = MacroL0MatcherSubscriber()
        await sub.on_macro_lifecycle(_Event())
        matcher_cache.invalidate_and_schedule_rebuild.assert_awaited_once()


class TestOtherSubscribers:
    @pytest.mark.asyncio
    async def test_app_map_superseded_obsoletes(self, monkeypatch):
        from types import SimpleNamespace

        import app.core.learning.macro.event.subscribers as subs

        called = {}

        async def fake_obsolete(app_map_id):
            called["id"] = app_map_id

        monkeypatch.setattr(subs, "mark_obsolete_by_app_map", fake_obsolete)
        sub = subs.MacroAppMapSubscriber()
        await sub.on_app_map_superseded(SimpleNamespace(data={"app_map_id": 9}))
        assert called == {"id": 9}
