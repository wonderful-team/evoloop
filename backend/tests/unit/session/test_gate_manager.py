"""组件/单元测试：ThreadGate + AgentSession 生命周期（parent-run-liveness §六·五 C1-C3）。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.core.engine.session.gate import GateEvent, ThreadGate
from app.core.engine.session.session import AgentSession


async def test_close_session_wakes_blocked_delivery_waiter() -> None:
    """值守串行等待：会话被停止/关闭时，wait_delivery_complete 必须返回（否则永久挂起）。"""
    from app.core.engine.session.session import _close_session

    session = AgentSession("t-unit-close-wake")

    waiter = asyncio.create_task(session.wait_delivery_complete())
    await asyncio.sleep(0)  # 让 waiter 挂起等待
    assert not waiter.done()

    # 停止/关闭会话（_close_session 会触发 delivery 通知）
    await _close_session(session)

    # wait_delivery_complete 应返回（不永久挂起）
    assert await asyncio.wait_for(waiter, timeout=1) is True
    assert session.lifecycle == "closed"


async def test_gate_basic_fifo() -> None:
    gate = ThreadGate()
    gate.put(GateEvent(kind="user_message", payload={"a": 1}))
    gate.put(GateEvent(kind="session_close"))
    first = await gate.wait_next()
    second = await gate.wait_next()
    assert first.kind == "user_message"
    assert first.payload == {"a": 1}
    assert second.kind == "session_close"


async def test_gate_drain_no_events() -> None:
    gate = ThreadGate()
    assert gate.drain() == []


async def test_gate_blocks_until_put() -> None:
    gate = ThreadGate()

    async def reader() -> str:
        ev = await gate.wait_next()
        return ev.kind

    task = asyncio.create_task(reader())
    await asyncio.sleep(0)
    assert not task.done()
    gate.put(GateEvent(kind="session_cancel"))
    assert await asyncio.wait_for(task, timeout=1) == "session_cancel"


async def test_session_lifecycle_cancel() -> None:
    session = AgentSession("t-unit-1")
    assert session.lifecycle == "running"

    with patch.object(session, "gate") as mock_gate, patch(
        "app.core.engine.session.session.activity_monitor", new=AsyncMock()
    ) as mock_monitor:
        await session.cancel("test")
        mock_gate.put.assert_called_once()
        mock_monitor.stop_run.assert_awaited_once_with("t-unit-1")
        ev = mock_gate.put.call_args.args[0]
        assert ev.kind == "session_cancel"

    session.worker = None

    from app.core.engine.session.session import _close_session

    await _close_session(session)
    assert session.lifecycle == "closed"
    assert getattr(session, "worker", None) is None


async def test_session_inject_resume() -> None:
    session = AgentSession("t-unit-2")
    with patch.object(session, "gate") as mock_gate:
        session.inject_resume("yes", is_cancel=False)
        ev = mock_gate.put.call_args.args[0]
        assert ev.kind == "user_message"
        assert ev.payload["hitl_resume_response"] == "yes"


async def test_session_manager_get_absent() -> None:
    from app.core.engine.session.manager import SessionManager

    manager = SessionManager()
    assert manager.get("t-unit-absent") is None


async def test_session_manager_get_or_create() -> None:
    from app.core.engine.session.manager import SessionManager

    manager = SessionManager()
    with patch(
        "app.core.engine.session.session.run_agent_session", new=AsyncMock()
    ):
        session = await manager.get_or_create("t-unit-3")
        assert session.thread_id == "t-unit-3"
        assert manager.get("t-unit-3") is session
        # idempotent
        again = await manager.get_or_create("t-unit-3")
        assert again is session
