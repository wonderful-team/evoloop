"""Unit tests for background runner security paths.

Covers the two regressions fixed in the consolidation:
- dangerous commands must be rejected on the ``background=True`` path too
- workspace-escape blocks must fail the task via the state machine so the
  error is visible to the agent and frontend.
"""

from __future__ import annotations

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


def _make_task(thread_id: str = "t1"):
    return task_manager.create_task(
        CreateBackgroundTaskRequest(
            task_type=TaskType.COMMAND,
            title="cmd",
            tool_name="execute_command",
            thread_id=thread_id,
        )
    )


async def test_execute_in_background_rejects_dangerous_command():
    result = await execute_in_background("rm -rf /", timeout=60, config=None)
    assert "Security Error" in result
    assert task_manager.get_active_tasks() == []


async def test_run_command_background_fails_dangerous_command():
    task = await _make_task()
    with patch(
        "app.core.execution.terminal.background.runner.get_working_directory",
        return_value="/proj",
    ):
        await run_command_background(task, "rm -rf /", timeout=60, config=None)

    assert task.status is TaskStatus.FAILED
    assert "Security Error" in task.error_message
    assert "Security Error" in task.get_recent_output()


async def test_run_command_background_fails_on_workspace_escape():
    task = await _make_task()
    with (
        patch(
            "app.core.execution.terminal.background.runner.get_working_directory",
            return_value="/proj",
        ),
        patch(
            "app.core.execution.terminal.background.runner.has_workspace_escape",
            return_value="cd /tmp",
        ),
    ):
        await run_command_background(task, "cd /tmp && pwd", timeout=60, config=None)

    assert task.status is TaskStatus.FAILED
    assert "允许的工作目录之外" in task.error_message
    assert "允许的工作目录之外" in task.get_recent_output()
