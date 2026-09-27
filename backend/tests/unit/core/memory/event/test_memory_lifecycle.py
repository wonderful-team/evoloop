"""Unit tests for MemoryLifecycleSubscriber (APP_STARTED init / APP_STOPPING shutdown)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.memory.event.subscribers import MemoryLifecycleSubscriber


async def test_app_started_initializes_memory():
    MemoryLifecycleSubscriber()
    with patch(
        "app.core.memory.lifespan.MemoryLifespanManager.ainitialize",
        new=AsyncMock(),
    ) as ainit:
        await MemoryLifecycleSubscriber().on_application_started(SimpleNamespace(data={}))
        ainit.assert_awaited_once()


async def test_app_started_swallows_init_failure():
    MemoryLifecycleSubscriber()
    with patch(
        "app.core.memory.lifespan.MemoryLifespanManager.ainitialize",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        await MemoryLifecycleSubscriber().on_application_started(SimpleNamespace(data={}))


async def test_app_stopping_shuts_down_memory():
    MemoryLifecycleSubscriber()
    with patch(
        "app.core.memory.lifespan.MemoryLifespanManager.shutdown",
        new=AsyncMock(),
    ) as shutdown:
        await MemoryLifecycleSubscriber().on_application_stopping(SimpleNamespace(data={}))
        shutdown.assert_awaited_once()
