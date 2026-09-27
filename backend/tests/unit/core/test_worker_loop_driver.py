"""验证 worker 事件循环持续驱动修复。

背景：worker 的事件循环原本只在每个 Huey 任务执行期间由 run_until_complete
驱动，任务间隙（~60s tick 间隔）循环空闲 → 值守 Agent 会话这类后台 asyncio
任务被冻结，几秒的 LLM 流式调用被拖慢上百倍（前端表现为"卡死"）。

修复：bin/run_worker.py 用后台线程 run_forever 持续驱动循环；
_run_async_task 在 loop 已被驱动时改走 run_coroutine_threadsafe（线程安全投递）。
"""

import asyncio
import threading
import time
from unittest.mock import AsyncMock, patch

from app.infrastructure.queue.huey_queue import HueyTaskScheduler


def _start_driven_loop():
    """启动一个被后台线程 run_forever 持续驱动的 event loop。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    return loop, thread


def _stop_loop(loop, thread):
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2)
    asyncio.set_event_loop(None)


def test_run_async_task_threadsafe_on_continuous_loop():
    """核心：loop 被持续驱动时，_run_async_task 走 run_coroutine_threadsafe，实时返回。"""
    loop, thread = _start_driven_loop()
    try:
        async def task(x):
            await asyncio.sleep(0.3)
            return x + 1

        sched = HueyTaskScheduler.__new__(HueyTaskScheduler)
        with patch(
            "app.infrastructure.database.resource_manager.db_resource_manager.initialize",
            new=AsyncMock(),
        ):
            start = time.monotonic()
            result = sched._run_async_task(task, False, 41)
            elapsed = time.monotonic() - start

        assert result == 42
        # 真实时间 ≈ 0.3s；修复前会被拖慢到远超此值
        assert elapsed < 1.5, f"_run_async_task 被拖慢: {elapsed:.2f}s (期望 <1.5s)"
    finally:
        _stop_loop(loop, thread)


def test_run_async_task_falls_back_when_loop_not_running():
    """loop 未被驱动时，_run_async_task 仍走 run_until_complete（测试/内嵌模式不回归）。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async def task(x):
            return x * 2

        sched = HueyTaskScheduler.__new__(HueyTaskScheduler)
        with patch(
            "app.infrastructure.database.resource_manager.db_resource_manager.initialize",
            new=AsyncMock(),
        ):
            result = sched._run_async_task(task, False, 21)
        assert result == 42
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def test_background_task_frozen_without_continuous_driver():
    """对照：loop 不被持续驱动时，后台任务不推进（旧行为/卡死根因）。"""
    loop = asyncio.new_event_loop()
    try:
        done = threading.Event()

        async def worker():
            await asyncio.sleep(0.05)
            done.set()

        loop.create_task(worker())
        time.sleep(0.3)  # 循环没在跑 → 任务不执行
        assert not done.is_set(), "未驱动时后台任务不应推进"

        loop.run_until_complete(asyncio.sleep(0.1))  # 一驱动即推进
        assert done.is_set(), "循环驱动后任务应推进"
    finally:
        loop.close()


def test_background_task_real_time_on_run_forever_loop():
    """核心机制：run_forever 持续驱动下，后台任务按真实时间推进。"""
    loop, thread = _start_driven_loop()
    try:
        done = threading.Event()
        start = time.monotonic()

        async def worker():
            await asyncio.sleep(0.5)
            done.set()

        fut = asyncio.run_coroutine_threadsafe(worker(), loop)
        fut.result(timeout=2.0)
        elapsed = time.monotonic() - start

        assert done.is_set()
        assert elapsed < 1.5, f"后台任务被拖慢: {elapsed:.2f}s (期望 ≈0.5s)"
    finally:
        _stop_loop(loop, thread)
