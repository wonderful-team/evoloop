"""Subagent event queue — routes subagent completion / HITL events to parent threads.

Design: docs/subagent-design.md §5.5 / §10 (event queue).
In-memory per-parent-thread queues; process restart loses queued events, so crash
recovery relies on the SubagentRun table instead. ``_subagent_queues[thread_id]``
must use ``__getitem__`` (triggers defaultdict creation) so events are never
silently dropped.
"""

import asyncio
import logging
from collections import defaultdict

from app.core.engine.session.gate import GateEvent
from app.core.engine.session.manager import session_manager
from app.core.events.schemas.subagent import (
    SUBAGENT_COMPLETED,
    SUBAGENT_HITL_REQUEST,
    SubagentCompletedEvent,
    SubagentHITLRequestEvent,
)

logger = logging.getLogger(__name__)

_subagent_queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
_subagent_hitl_queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)

_listener_registered = False


async def _on_subagent_completed(event: SubagentCompletedEvent) -> None:
    # __getitem__ 触发 defaultdict 创建；不能用 .get()，否则 key 缺失时事件被丢弃。
    q = _subagent_queues[event.thread_id]
    await q.put(event)
    _wake_session(event.thread_id, "subagent_completed", event.subagent_id)


async def _on_subagent_hitl_request(event: SubagentHITLRequestEvent) -> None:
    q = _subagent_hitl_queues[event.thread_id]
    await q.put(event)
    _wake_session(event.thread_id, "subagent_hitl_request", event.subagent_id)


def _wake_session(parent_thread_id: str, kind: str, subagent_id: str) -> None:
    """Wake the parent session main loop (session gate) if it's alive.

    The parent Supervisor parks on its ThreadGate while subagents run; queuing an
    event alone won't wake it. If no live session, the event stays queued until the
    next message injection drains it (crash recovery covers the rest).
    """
    try:

        session = session_manager.get(parent_thread_id)
        if session is not None:
            session.gate.put(
                GateEvent(kind=kind, payload={"subagent_id": subagent_id})
            )
    except Exception as e:  # 底座未就绪（过渡期）时静默跳过，drain 逻辑仍可用
        logger.debug(f"[SubagentEvents] gate wake skipped: {e}")


def ensure_listener() -> None:
    """Register the system_bus subscriber exactly once."""
    global _listener_registered
    if _listener_registered:
        return
    from app.core.events import system_bus

    system_bus.subscribe(SUBAGENT_COMPLETED, _on_subagent_completed)
    system_bus.subscribe(SUBAGENT_HITL_REQUEST, _on_subagent_hitl_request)
    _listener_registered = True


async def drain_subagent_events(thread_id: str) -> list[dict]:
    """Drain completed events for a parent thread."""
    ensure_listener()
    q = _subagent_queues[thread_id]
    events = []
    while not q.empty():
        event = q.get_nowait()
        events.append(event.model_dump())
    return events


async def drain_subagent_hitl_requests(thread_id: str) -> list[SubagentHITLRequestEvent]:
    """Drain HITL request events for a parent thread."""
    ensure_listener()
    q = _subagent_hitl_queues[thread_id]
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    return events
