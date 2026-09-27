"""SchedulerLifecycleSubscriber — tick 心跳随 APP_STARTED/APP_STOPPING 启停。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


@pytest.fixture
def sub():
    from app.infrastructure.scheduler.lifecycle import SchedulerLifecycleSubscriber

    return SchedulerLifecycleSubscriber()


@pytest.fixture
def stub_tick(monkeypatch):
    """SchedulerService.tick 换成记录型桩：首次调用后置事件。"""
    state = {"ticks": 0, "ticked": asyncio.Event()}

    async def _fake_tick() -> None:
        state["ticks"] += 1
        state["ticked"].set()

    monkeypatch.setattr(
        "app.infrastructure.scheduler.service.SchedulerService.tick", _fake_tick
    )
    return state


def _event():
    return SimpleNamespace()


async def test_app_started_runs_tick_loop(sub, stub_tick):
    await sub.on_app_started(_event())
    await asyncio.wait_for(stub_tick["ticked"].wait(), timeout=2)
    assert stub_tick["ticks"] == 1
    assert sub.tick_task is not None
    assert sub.tick_task.get_name() == "duty-scheduler-tick"

    await sub.on_app_stopping(_event())
    assert sub.tick_task is None


async def test_duplicate_start_ignored(sub, stub_tick):  # noqa: ARG001 — patch 副作用
    await sub.on_app_started(_event())
    first = sub.tick_task
    await sub.on_app_started(_event())
    assert sub.tick_task is first

    await sub.on_app_stopping(_event())
    assert sub.tick_task is None


async def test_app_stopping_cancels_during_sleep(sub, stub_tick):  # noqa: ARG001 — patch 副作用
    """sleep(60) 期间停止 → 立即取消，不等 sleep 结束"""
    await sub.on_app_started(_event())
    await asyncio.wait_for(stub_tick["ticked"].wait(), timeout=2)
    await sub.on_app_stopping(_event())
    assert sub.tick_task is None


async def test_tick_exception_does_not_kill_loop(sub, stub_tick, monkeypatch):
    """tick 抛异常 → 循环捕获继续（不因单次失败停摆）"""
    deaths = {"n": 0}

    async def _failing_tick() -> None:
        deaths["n"] += 1
        if deaths["n"] == 1:
            raise RuntimeError("boom")
        stub_tick["ticked"].set()

    monkeypatch.setattr(
        "app.infrastructure.scheduler.service.SchedulerService.tick", _failing_tick
    )
    monkeypatch.setattr(
        "app.infrastructure.scheduler.lifecycle.TICK_INTERVAL_SECONDS", 0.01
    )
    await sub.on_app_started(_event())
    await asyncio.wait_for(stub_tick["ticked"].wait(), timeout=2)
    assert deaths["n"] == 2  # 第一次失败后循环存活并二次执行

    await sub.on_app_stopping(_event())


async def test_stopping_without_start_noop(sub):
    await sub.on_app_stopping(_event())
    assert sub.tick_task is None
