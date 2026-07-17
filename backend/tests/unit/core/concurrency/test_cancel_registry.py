"""CancelRegistry tests — mid-execution cancellation."""

import asyncio

import pytest

from app.core.concurrency import CancelRegistry


class TestCancelRegistry:
    """CancelRegistry — task handle retention + zero-latency cancel."""

    @pytest.mark.asyncio
    async def test_register_and_unregister(self):
        reg = CancelRegistry()
        run = await reg.register("t1", task=None, owner_id=42)

        assert run.thread_id == "t1"
        assert run.owner_id == 42
        assert "t1" in reg.active_runs()
        assert reg.active_count() == 1

        await reg.unregister("t1")
        assert reg.active_count() == 0

    @pytest.mark.asyncio
    async def test_is_cancelled_false_before_cancel(self):
        reg = CancelRegistry()
        await reg.register("t1")

        assert not reg.is_cancelled("t1")

    @pytest.mark.asyncio
    async def test_cancel_sets_event(self):
        reg = CancelRegistry()
        await reg.register("t1")

        cancelled = await reg.cancel("t1", requester_id=99)

        assert cancelled
        assert reg.is_cancelled("t1")

    @pytest.mark.asyncio
    async def test_cancel_unknown_returns_false(self):
        reg = CancelRegistry()
        result = await reg.cancel("nonexistent")
        assert not result

    @pytest.mark.asyncio
    async def test_cancel_calls_task_cancel(self):
        reg = CancelRegistry()

        cancelled_flag = asyncio.Event()

        async def long_running():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled_flag.set()
                raise

        task = asyncio.create_task(long_running())
        await reg.register("t1", task=task, owner_id=1)

        await asyncio.sleep(0.05)
        await reg.cancel("t1")

        await asyncio.sleep(0.05)
        assert cancelled_flag.is_set()

    @pytest.mark.asyncio
    async def test_cancel_propagates_to_children(self):
        reg = CancelRegistry()

        await reg.register("parent", task=None, owner_id=1)
        await reg.register("child1", task=None, parent_thread_id="parent")
        await reg.register("child2", task=None, parent_thread_id="parent")

        await reg.cancel("parent")

        assert reg.is_cancelled("parent")
        assert reg.is_cancelled("child1")
        assert reg.is_cancelled("child2")

    @pytest.mark.asyncio
    async def test_cancel_all(self):
        reg = CancelRegistry()
        await reg.register("t1")
        await reg.register("t2")
        await reg.register("t3")

        count = await reg.cancel_all()

        assert count == 3
        assert reg.is_cancelled("t1")
        assert reg.is_cancelled("t2")
        assert reg.is_cancelled("t3")

    @pytest.mark.asyncio
    async def test_is_cancelled_unregistered_returns_false(self):
        reg = CancelRegistry()
        assert not reg.is_cancelled("never_registered")

    @pytest.mark.asyncio
    async def test_get_run_returns_registered_run(self):
        reg = CancelRegistry()
        await reg.register("t1", owner_id=42)

        run = await reg.get_run("t1")
        assert run is not None
        assert run.owner_id == 42
