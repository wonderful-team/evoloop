"""Unit tests for BackgroundTaskLifecycleSubscriber (APP_STARTED / APP_STOPPING)."""

from __future__ import annotations

import asyncio

import pytest

from app.core.events import system_bus
from app.core.events.schemas import AppStartedEvent, AppStoppingEvent
from app.core.execution.terminal.background import task_manager
from app.core.execution.terminal.background.event.subscribers import (
    BackgroundTaskLifecycleSubscriber,
)


@pytest.fixture(autouse=True)
async def _reset_cleanup_task():
    async def _stop_current():
        cleanup = getattr(task_manager, "_cleanup_task", None)
        if cleanup is not None and not cleanup.done():
            cleanup.cancel()
            try:
                await cleanup
            except asyncio.CancelledError:
                pass
        task_manager._cleanup_task = None

    await _stop_current()
    yield
    await _stop_current()


async def test_app_started_starts_cleanup_worker():
    BackgroundTaskLifecycleSubscriber()
    await system_bus.publish(AppStartedEvent(source="test", data={}))

    cleanup = task_manager._cleanup_task
    assert cleanup is not None
    assert not cleanup.done()


async def test_app_stopping_cancels_cleanup_worker():
    BackgroundTaskLifecycleSubscriber()
    await system_bus.publish(AppStartedEvent(source="test", data={}))
    cleanup = task_manager._cleanup_task

    await system_bus.publish(AppStoppingEvent(source="test", data={}))

    assert cleanup.done()
