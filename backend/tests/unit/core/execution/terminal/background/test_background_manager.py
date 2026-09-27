"""Unit tests for BackgroundTaskManager state machine and indexes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

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


@pytest.fixture
def publish():
    with (
        patch("app.core.events.system_bus.publish", new=AsyncMock()) as mock_publish,
        patch(
            "app.core.monitoring.activity.activity_monitor.record_task_update",
            new=AsyncMock(),
        ),
    ):
        yield mock_publish


def _make_request(
    thread_id: str = "thread-1",
    title: str = "echo hi",
    tool_name: str = "execute_command",
    metadata: dict | None = None,
) -> CreateBackgroundTaskRequest:
    return CreateBackgroundTaskRequest(
        task_type=TaskType.COMMAND,
        title=title,
        tool_name=tool_name,
        thread_id=thread_id,
        metadata=metadata,
    )


async def test_create_task_initial_state():
    task = await task_manager.create_task(_make_request())
    assert task.status is TaskStatus.PENDING
    assert task.task_id.startswith("com-")
    assert task_manager.get_task(task.task_id) is task


async def test_lifecycle_transitions():
    task = await task_manager.create_task(_make_request(thread_id="t1"))

    assert await task_manager.start_task(task.task_id, process_id=1234) is True
    assert task.status is TaskStatus.RUNNING
    assert task.process_id == 1234
    assert task.is_running

    assert await task_manager.complete_task(task.task_id, result={"exit_code": 0}) is True
    assert task.status is TaskStatus.COMPLETED
    assert task.result == {"exit_code": 0}
    assert task.is_completed
    assert task.completed_at is not None

    # Terminal states reject further transitions
    assert await task_manager.fail_task(task.task_id, error="boom") is False
    assert await task_manager.cancel_task(task.task_id) is False


async def test_fail_timeout_cancel():
    failed = await task_manager.create_task(_make_request())
    await task_manager.start_task(failed.task_id)
    assert await task_manager.fail_task(failed.task_id, error="boom") is True
    assert failed.status is TaskStatus.FAILED
    assert failed.error_message == "boom"

    timed_out = await task_manager.create_task(_make_request())
    await task_manager.start_task(timed_out.task_id)
    assert await task_manager.timeout_task(timed_out.task_id) is True
    assert timed_out.status is TaskStatus.TIMEOUT

    cancelled = await task_manager.create_task(_make_request())
    await task_manager.start_task(cancelled.task_id)
    fired: list[bool] = []
    cancelled.set_cancel_callback(lambda: fired.append(True))
    assert await task_manager.cancel_task(cancelled.task_id) is True
    assert cancelled.status is TaskStatus.CANCELLED
    assert fired == [True]


async def test_output_roundtrip():
    task = await task_manager.create_task(_make_request())
    task_manager.append_output(task.task_id, "line1\n")
    task_manager.append_output(task.task_id, "line2")
    assert task.get_recent_output(10) == "line1\nline2"
    assert task.get_recent_output(1) == "line2"


async def test_indexes_and_query_methods():
    first = await task_manager.create_task(_make_request(thread_id="t1"))
    await task_manager.create_task(_make_request(thread_id="t1"))
    await task_manager.create_task(_make_request(thread_id="t2"))

    thread_ids = {t.task_id for t in task_manager.get_thread_tasks("t1")}
    assert len(thread_ids) == 2

    assert len(task_manager.get_active_tasks("t1")) == 2
    assert len(task_manager.get_active_tasks()) == 3

    await task_manager.start_task(first.task_id)
    running = task_manager.get_running_tasks(tool_name="execute_command")
    assert [t.task_id for t in running] == [first.task_id]


async def test_lifecycle_events_published(publish):
    task = await task_manager.create_task(_make_request())
    await task_manager.start_task(task.task_id)
    await task_manager.complete_task(task.task_id)

    actions = [call.args[0].action for call in publish.await_args_list]
    assert actions == ["created", "started", "completed"]


async def test_output_event_published_when_streaming_enabled(publish):
    import asyncio

    task = await task_manager.create_task(
        _make_request(metadata={"enable_streaming_output": True})
    )
    task_manager.append_output(task.task_id, "hello")
    await asyncio.sleep(0.05)

    outputs = [getattr(call.args[0], "output", None) for call in publish.await_args_list]
    assert "hello" in outputs


async def test_max_tasks_per_thread_evicts_oldest_completed():
    for i in range(50):
        await task_manager.create_task(_make_request(thread_id="t1", title=f"t{i}"))
    oldest = task_manager.get_thread_tasks("t1")[-1]
    await task_manager.complete_task(oldest.task_id)

    await task_manager.create_task(_make_request(thread_id="t1", title="overflow"))
    assert oldest.task_id not in task_manager._tasks
    assert len(task_manager.get_thread_tasks("t1")) == 50


async def test_max_tasks_per_thread_raises_when_all_active():
    for _ in range(50):
        await task_manager.create_task(_make_request(thread_id="t1"))
    with pytest.raises(RuntimeError):
        await task_manager.create_task(_make_request(thread_id="t1"))


async def test_stats():
    await task_manager.create_task(_make_request(thread_id="t1"))
    await task_manager.create_task(_make_request(thread_id="t1"))
    stats = task_manager.get_stats()
    assert stats.total_tasks == 2
    assert stats.by_status[TaskStatus.PENDING.value] == 2
    assert stats.by_thread == 1
    assert stats.by_tool["execute_command"] == 2


async def test_background_task_to_dict():
    task = await task_manager.create_task(_make_request(thread_id="t1"))
    task_manager.append_output(task.task_id, "line1")
    await task_manager.start_task(task.task_id, process_id=42)

    data = task.to_dict()
    assert data["task_id"] == task.task_id
    assert data["status"] == "running"
    assert data["task_type"] == "command"
    assert data["is_running"] is True
    assert data["is_completed"] is False
    assert data["can_cancel"] is True
    assert data["process_id"] == 42
    assert data["output"] == "line1"
    assert "created_at" in data
    assert "display_title" in data


async def test_background_task_properties():
    task = await task_manager.create_task(_make_request())
    assert task.is_running is False
    assert task.can_cancel is True  # PENDING is cancellable
    assert task.elapsed_seconds >= 0

    await task_manager.start_task(task.task_id)
    assert task.is_running is True

    await task_manager.complete_task(task.task_id)
    assert task.is_completed is True
    assert task.can_cancel is False


async def test_thread_tasks_exclude_completed():
    task = await task_manager.create_task(_make_request(thread_id="t1"))
    await task_manager.complete_task(task.task_id)

    assert task_manager.get_thread_tasks("t1", include_completed=False) == []
