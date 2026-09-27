"""scheduler 按种类串行队列机制：同类跳过、异类排队。

调度协调器（_exec_lock/_active_kinds）是模块级异步单例，绑定到事件循环。
生产单 worker 单循环；测试用 session 级 event_loop 共享同一循环，
保证跨测试函数复用该单例不炸。
"""

import asyncio

import pytest

from app.core.channel.duty import scheduler


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def test_same_kind_skips_while_running():
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_run():
        started.set()
        await release.wait()

    first = asyncio.create_task(scheduler._run_kind("wecom", slow_run))
    await started.wait()
    # 同类任务：应直接跳过（None），不等待
    second = asyncio.create_task(scheduler._run_kind("wecom", slow_run))
    await asyncio.sleep(0.01)
    assert second.done()
    assert await second == None  # noqa: E711 — 显式断言跳过返回 None
    release.set()
    await first
    # 前一个完成后，同类任务可再执行
    done = await scheduler._run_kind("wecom", lambda: asyncio.sleep(0, result=5))
    assert done == 5


async def test_different_kinds_queue_not_skip():
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_run():
        started.set()
        await release.wait()
        return 7

    first = asyncio.create_task(scheduler._run_kind("wecom", slow_run))
    await started.wait()
    # 不同种类：不跳过，排队等全局串行锁
    second = asyncio.create_task(
        scheduler._run_kind("business_poll", lambda: asyncio.sleep(0, result=3))
    )
    await asyncio.sleep(0.01)
    assert not second.done()
    release.set()
    assert await first == 7
    assert await second == 3


async def test_different_projects_same_kind_serialized():
    order: list[str] = []

    async def make(name: str, hold: asyncio.Event) -> callable:
        async def run():
            order.append(f"{name}:start")
            if hold is not None:
                await hold.wait()
            order.append(f"{name}:end")
            return 1

        return run

    release = asyncio.Event()
    a = asyncio.create_task(
        scheduler._run_kind("wecom", await make("a", release))
    )
    b = asyncio.create_task(scheduler._run_kind("wecom", await make("b", None)))
    await asyncio.sleep(0.05)
    # b 到达时 a 还在跑 → b 立即被跳过（已完成，未进入执行）
    assert b.done()
    await b
    release.set()
    await a
    assert "b:start" not in order
    assert order.count("a:start") == 1 and order.count("a:end") == 1


async def test_queued_same_kind_also_skips():
    """同类任务已在队列中等待（未执行）时，新到同类也跳过。"""
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_wecom():
        started.set()
        await release.wait()
        return 1

    async def fast_business_poll():
        return 2

    # wecom 在执行中 → business_poll 排队等锁
    wecom = asyncio.create_task(scheduler._run_kind("wecom", slow_wecom))
    await started.wait()
    queued = asyncio.create_task(
        scheduler._run_kind("business_poll", fast_business_poll)
    )
    await asyncio.sleep(0.01)
    assert not queued.done()  # 队列中等待（异类不跳过）
    # 队列中已有 business_poll → 新到同类直接跳过
    later = asyncio.create_task(
        scheduler._run_kind("business_poll", fast_business_poll)
    )
    await asyncio.sleep(0.01)
    assert later.done()
    assert await later is None
    # 释放 wecom，queued 随后正常执行
    release.set()
    await wecom
    assert await queued == 2
