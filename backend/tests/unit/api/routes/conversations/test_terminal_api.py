"""Unit tests for the terminal API endpoints in conversations/terminal.py."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.routes.conversations import terminal
from app.api.routes.conversations.terminal import (
    TerminalCommandRequest,
    TerminalInputRequest,
    get_active_thread_tasks,
    run_terminal_command,
    send_terminal_input,
)
from app.core.execution.terminal.background import (
    CreateBackgroundTaskRequest,
    TaskStatus,
    TaskType,
    task_manager,
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


@pytest.fixture(autouse=True)
def _mock_hydration():
    with patch(
        "app.api.routes.conversations.terminal._hydrate_thread_working_directory",
        new=AsyncMock(),
    ):
        yield


async def test_run_terminal_command_creates_and_completes_task():
    with patch.object(
        terminal.terminal_manager, "run_command", return_value=("hello\n", "", 0)
    ):
        resp = await run_terminal_command(
            "thread-1", TerminalCommandRequest(command="echo hello")
        )
        task = await _wait_status(resp["task_id"])

    assert task.status is TaskStatus.COMPLETED
    assert task.tool_name == "user_terminal"


async def test_run_terminal_command_fails_task_on_nonzero_exit():
    with patch.object(
        terminal.terminal_manager, "run_command", return_value=("", "boom", 2)
    ):
        resp = await run_terminal_command(
            "thread-1", TerminalCommandRequest(command="false")
        )
        task = await _wait_status(resp["task_id"])

    assert task.status is TaskStatus.FAILED
    assert "Exited with code 2" in task.error_message


async def test_send_terminal_input_writes_to_pty():
    pty = MagicMock()
    pty._master_fd = 1
    session = MagicMock()
    session.pty = pty

    with (
        patch.object(terminal.terminal_manager, "get_session_for_thread", return_value=None),
        patch.object(terminal.terminal_manager, "get_session", return_value=session),
    ):
        resp = await send_terminal_input("thread-1", TerminalInputRequest(text="ls -la"))

    assert resp == {"status": "ok"}
    pty.write_raw.assert_called_once_with("ls -la".encode("utf-8", errors="replace"))


async def test_get_active_thread_tasks():
    await task_manager.create_task(
        CreateBackgroundTaskRequest(
            task_type=TaskType.COMMAND,
            title="active task",
            tool_name="execute_command",
            thread_id="thread-1",
        )
    )

    tasks = await get_active_thread_tasks("thread-1")
    assert len(tasks) == 1
    assert tasks[0]["title"] == "active task"
    assert tasks[0]["status"] == "pending"


async def _wait_status(task_id: str, deadline: float = 10.0):
    start = asyncio.get_running_loop().time()
    while True:
        task = task_manager.get_task(task_id)
        if task is None or task.is_completed:
            return task
        if asyncio.get_running_loop().time() - start > deadline:
            raise AssertionError(f"task {task_id} did not finish: {task.status}")
        await asyncio.sleep(0.05)
