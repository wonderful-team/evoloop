"""SupervisorLifecycleSubscriber — supervisor 随 APP_STARTED/APP_STOPPING 启停。"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def sub():
    from app.domain.tasks.event.subscribers import SupervisorLifecycleSubscriber

    return SupervisorLifecycleSubscriber()


@pytest.fixture
def stub_forever(monkeypatch):
    """run_supervisor_forever 换成可等待的挂起桩，记录启动次数。"""
    started = {"n": 0}

    async def _stub() -> None:
        started["n"] += 1
        await asyncio.Event().wait()  # 挂起直至被取消

    monkeypatch.setattr(
        "app.domain.tasks.runtime.supervisor.run_supervisor_forever", _stub
    )
    return started


async def test_app_started_spawns_supervisor(sub, stub_forever):
    await sub.on_app_started(SimpleNamespaceEvent())
    await asyncio.sleep(0)  # 让渡事件循环：stub 首步执行
    assert stub_forever["n"] == 1
    assert sub.supervisor_task is not None
    assert not sub.supervisor_task.done()
    assert sub.supervisor_task.get_name() == "duty-supervisor"

    await sub.on_app_stopping(SimpleNamespaceEvent())
    assert sub.supervisor_task is None
    assert sub.supervisor_task is None or True


async def test_duplicate_start_ignored(sub, stub_forever):
    await sub.on_app_started(SimpleNamespaceEvent())
    await asyncio.sleep(0)
    first = sub.supervisor_task
    await sub.on_app_started(SimpleNamespaceEvent())  # 幂等：不重复拉起
    assert sub.supervisor_task is first
    assert stub_forever["n"] == 1

    await sub.on_app_stopping(SimpleNamespaceEvent())


async def test_app_stopping_cancels_supervisor(sub, stub_forever):  # noqa: ARG001 — patch 副作用
    await sub.on_app_started(SimpleNamespaceEvent())
    task = sub.supervisor_task
    await sub.on_app_stopping(SimpleNamespaceEvent())
    assert task.cancelled()
    assert sub.supervisor_task is None


async def test_stopping_without_start_noop(sub):
    await sub.on_app_stopping(SimpleNamespaceEvent())  # 不抛异常
    assert sub.supervisor_task is None


# ── helper ────────────────────────────────────────────────


def SimpleNamespaceEvent():
    """生命周期事件桩（handler 不读事件字段）。"""
    from types import SimpleNamespace

    return SimpleNamespace()


async def test_startup_reconcile_failure_does_not_kill_supervisor(monkeypatch):
    """启动 reconcile 抛异常 → 主循环存活继续 drain（稳态 reconcile 兜底）"""
    from app.domain.tasks.runtime import supervisor

    calls = {"reconcile": 0, "drain": 0}

    async def _failing_reconcile(*_a, **_k):  # noqa: ARG001
        calls["reconcile"] += 1
        raise RuntimeError("db down")

    async def _fake_drain():
        calls["drain"] += 1
        if calls["drain"] >= 2:
            raise asyncio.CancelledError  # 用取消退出测试循环

    async def _fake_wait(_timeout):
        await asyncio.sleep(0)

    monkeypatch.setattr(supervisor, "reconcile_stranded", _failing_reconcile)
    monkeypatch.setattr(supervisor, "dispatch_due_tasks", _fake_drain)
    monkeypatch.setattr(supervisor, "wait_duty_wakeup", _fake_wait)

    task = asyncio.create_task(supervisor.run_supervisor_forever())
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=2)
    assert calls["reconcile"] == 1  # 只在启动时调用一次且失败被吞
    assert calls["drain"] == 2  # 主循环存活并继续 drain


async def test_supervisor_crash_is_visible(sub, monkeypatch, caplog):
    """主循环异常退出（非取消）→ CRITICAL 日志（值守停摆必须被看见）"""
    import logging

    async def _crashing() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.domain.tasks.runtime.supervisor.run_supervisor_forever", _crashing
    )
    with caplog.at_level(logging.CRITICAL):
        await sub.on_app_started(SimpleNamespaceEvent())
        await asyncio.sleep(0.05)  # 让任务跑完并触发 done-callback

    assert any(
        r.levelno == logging.CRITICAL and "值守已停摆" in r.message
        for r in caplog.records
    )
    # 句柄保留（不重置），便于事后检查
    assert sub.supervisor_task is not None
    assert sub.supervisor_task.done()
