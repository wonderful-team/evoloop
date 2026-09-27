"""Unit tests for SandboxLifecycleSubscriber (APP_STOPPING teardown)."""

from __future__ import annotations

from unittest.mock import patch

from app.core.events import system_bus
from app.core.events.schemas import AppStoppingEvent
from app.core.execution.sandbox.event.subscribers import SandboxLifecycleSubscriber


async def test_app_stopping_calls_factory_reset():
    SandboxLifecycleSubscriber()
    with patch(
        "app.core.execution.sandbox.factory.SandboxFactory.reset"
    ) as reset:
        await system_bus.publish(AppStoppingEvent(source="test", data={}))
        reset.assert_called_once()
