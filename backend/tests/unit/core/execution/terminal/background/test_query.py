"""Unit tests for cancel_command tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.execution.terminal.background import (
    CreateBackgroundTaskRequest,
    TaskType,
    task_manager,
)
from app.core.execution.terminal.tools.query import cancel_command


@pytest.fixture(autouse=True)
def _reset_manager():
    task_manager._tasks.clear()
    task_manager._thread_index.clear()
    task_manager._tool_index.clear()
    task_manager._status_index.clear()
    yield


@pytest.fixture(autouse=True)
def _mock_events():
    with (
        patch("app.core.events.system_bus.publish", new=AsyncMock()),
        patch(
            "app.core.monitoring.activity.activity_monitor.record_task_update",
            new=AsyncMock(),
        ),
    ):
        yield


async def _make_task(title: str = "echo hi"):
    return await task_manager.create_task(
        CreateBackgroundTaskRequest(
            task_type=TaskType.COMMAND,
            title=title,
            tool_name="execute_command",
            thread_id="t1",
        )
    )


async def test_cancel_command_cancels_running_task():
    task = await _make_task()
    await task_manager.start_task(task.task_id)

    out = await cancel_command(task.task_id)
    assert "Task cancelled" in out
    assert task.status.value == "cancelled"


async def test_cancel_command_completed_task_rejected():
    task = await _make_task()
    await task_manager.complete_task(task.task_id)

    out = await cancel_command(task.task_id)
    assert "already completed" in out


async def test_cancel_command_missing_task():
    out = await cancel_command("nope-00000000")
    assert "Task not found" in out
