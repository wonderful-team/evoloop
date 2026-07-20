"""Tests for VoiceTaskRegistry (register / cancel via WorkerRegistry)."""

import asyncio

import pytest

from app.core.routing.executor import cancel_voice_task, register_voice_task
from app.core.engine.worker_registry import worker_registry


@pytest.mark.asyncio
async def test_register_and_cancel() -> None:
    async def long_task() -> str:
        await asyncio.sleep(10)
        return "done"

    task = asyncio.create_task(long_task())
    await register_voice_task("thread-cancel-test", task)

    record = await worker_registry.get_worker("thread-cancel-test")
    assert record is not None
    assert record.status == "running"

    cancelled = await cancel_voice_task("thread-cancel-test")
    assert cancelled is True

    record = await worker_registry.get_worker("thread-cancel-test")
    assert record is None

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_cancel_nonexistent_returns_false() -> None:
    result = await cancel_voice_task("nonexistent-thread")
    assert result is False


@pytest.mark.asyncio
async def test_cancel_completed_task_returns_false() -> None:
    async def quick() -> str:
        return "done"

    task = asyncio.create_task(quick())
    await task
    await register_voice_task("thread-done", task)
    result = await cancel_voice_task("thread-done")
    assert result is False


@pytest.mark.asyncio
async def test_register_replaces_record() -> None:
    async def long_task() -> str:
        await asyncio.sleep(10)
        return "done"

    old_task = asyncio.create_task(long_task())
    await register_voice_task("thread-replace", old_task)

    # Old task should still be running after registration (no auto-cancel anymore)
    assert not old_task.done()

    new_task = asyncio.create_task(long_task())
    await register_voice_task("thread-replace", new_task)

    # New record should point to new_task
    record = await worker_registry.get_worker("thread-replace")
    assert record is not None
    assert record.task is new_task

    # Old task should still be running (new register does not auto-cancel)
    assert not old_task.done()

    await cancel_voice_task("thread-replace")
    old_task.cancel()
