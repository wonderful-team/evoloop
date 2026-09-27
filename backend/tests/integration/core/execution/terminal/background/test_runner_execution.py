"""Integration tests for runner background execution with real subprocesses.

Covers the normal completion / failure / timeout paths of
``run_command_background`` and the end-to-end ``execute_in_background`` flow.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.execution.terminal.background import (
    CreateBackgroundTaskRequest,
    TaskStatus,
    TaskType,
    task_manager,
)
from app.core.execution.terminal.background.runner import (
    execute_in_background,
    run_command_background,
)


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


async def _make_task(command: str = "cmd"):
    return await task_manager.create_task(
        CreateBackgroundTaskRequest(
            task_type=TaskType.COMMAND,
            title=command,
            tool_name="execute_command",
            thread_id="t1",
        )
    )


async def _wait_status(task_id: str, deadline: float = 10.0):
    """Poll until the task reaches a terminal state."""
    start = asyncio.get_running_loop().time()
    while True:
        task = task_manager.get_task(task_id)
        if task is None or task.is_completed:
            return task
        if asyncio.get_running_loop().time() - start > deadline:
            raise AssertionError(f"task {task_id} did not finish: {task.status}")
        await asyncio.sleep(0.05)


async def test_run_command_background_completes():
    task = await _make_task("echo runner-ok")
    await run_command_background(task, "echo runner-ok", timeout=10, config=None)

    assert task.status is TaskStatus.COMPLETED
    assert task.result == {"exit_code": 0}
    assert "runner-ok" in task.get_recent_output()


async def test_run_command_background_fails_on_nonzero_exit():
    task = await _make_task("exit 3")
    await run_command_background(task, "exit 3", timeout=10, config=None)

    assert task.status is TaskStatus.FAILED
    assert "Command exited with code 3" in task.error_message


async def test_run_command_background_times_out():
    task = await _make_task("sleep 30")
    await run_command_background(task, "sleep 30", timeout=1, config=None)

    assert task.status is TaskStatus.TIMEOUT


async def test_execute_in_background_full_flow():
    result = await execute_in_background("echo bg-ok", timeout=10, config=None)

    assert "Background task started" in result
    task_id = result.split("`")[1]

    task = await _wait_status(task_id)
    assert task is not None
    assert task.status is TaskStatus.COMPLETED
    assert "bg-ok" in task.get_recent_output()
