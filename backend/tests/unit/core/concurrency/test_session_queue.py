"""SessionSerialQueue tests — per-thread FIFO serialization."""

import asyncio

import pytest

from app.core.concurrency import SessionSerialQueue


class TestSessionSerialQueue:
    """SessionSerialQueue — per-thread serial execution gate."""

    @pytest.mark.asyncio
    async def test_single_acquire_release(self):
        queue = SessionSerialQueue()
        slot = await queue.acquire("t1", timeout=1.0)
        assert slot.thread_id == "t1"
        assert queue.is_active("t1")
        await queue.release("t1")
        assert not queue.is_active("t1")

    @pytest.mark.asyncio
    async def test_concurrent_same_thread_serialized(self):
        """Two coroutines on the same thread execute serially."""
        queue = SessionSerialQueue()
        execution_order = []

        async def worker(name):
            async with await queue.acquire("t1", timeout=5.0):
                execution_order.append(f"{name}_start")
                await asyncio.sleep(0.05)
                execution_order.append(f"{name}_end")

        await asyncio.gather(worker("A"), worker("B"))

        assert execution_order == ["A_start", "A_end", "B_start", "B_end"]

    @pytest.mark.asyncio
    async def test_different_threads_parallel(self):
        """Different threads execute in parallel."""
        queue = SessionSerialQueue()
        execution_order = []

        async def worker(thread_id, name):
            async with await queue.acquire(thread_id, timeout=5.0):
                execution_order.append(f"{name}_start")
                await asyncio.sleep(0.05)
                execution_order.append(f"{name}_end")

        await asyncio.gather(
            worker("t1", "A"),
            worker("t2", "B"),
        )

        starts = [e for e in execution_order if e.endswith("_start")]
        assert len(starts) == 2
        assert "A_start" in starts and "B_start" in starts

    @pytest.mark.asyncio
    async def test_timeout_on_held_lock(self):
        """Acquire times out when lock is held and not released."""
        queue = SessionSerialQueue()
        await queue.acquire("t1", timeout=0.1)

        with pytest.raises(asyncio.TimeoutError):
            await queue.acquire("t1", timeout=0.1)

        await queue.release("t1")

    @pytest.mark.asyncio
    async def test_queue_depth_tracking(self):
        """get_queue_depth reports waiter count."""
        queue = SessionSerialQueue()
        await queue.acquire("t1", timeout=1.0)

        assert queue.get_queue_depth("t1") == 0

        async def waiter():
            try:
                await queue.acquire("t1", timeout=5.0)
            except asyncio.TimeoutError:
                pass

        task = asyncio.create_task(waiter())
        await asyncio.sleep(0.05)

        assert queue.get_queue_depth("t1") >= 1

        await queue.release("t1")
        await task

    @pytest.mark.asyncio
    async def test_active_sessions(self):
        """active_sessions lists threads with held slots."""
        queue = SessionSerialQueue()
        await queue.acquire("t1", timeout=1.0)
        await queue.acquire("t2", timeout=1.0)

        active = queue.active_sessions()
        assert "t1" in active
        assert "t2" in active

        await queue.release("t1")
        await queue.release("t2")

    @pytest.mark.asyncio
    async def test_cleanup_removes_stale(self):
        """cleanup removes locks with no active holders."""
        queue = SessionSerialQueue()
        await queue.acquire("t1", timeout=1.0)
        await queue.release("t1")

        await queue.cleanup()

        assert "t1" not in queue._locks
