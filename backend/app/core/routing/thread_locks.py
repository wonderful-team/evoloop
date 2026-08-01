"""Shared per-thread locks for route serialization.

Both chat and voice routes must serialize per-thread to prevent concurrent
agent runs from corrupting conversation state or starting overlapping workers.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from app.core.context import ContextManager, EvoContext

_thread_locks: dict[str, asyncio.Lock] = {}
_thread_locks_guard = asyncio.Lock()


async def get_thread_lock(thread_id: str) -> asyncio.Lock:
    """Get or create a per-thread async lock for route serialization."""
    async with _thread_locks_guard:
        if thread_id not in _thread_locks:
            _thread_locks[thread_id] = asyncio.Lock()
        return _thread_locks[thread_id]


@asynccontextmanager
async def route_lock_scope(
    thread_id: str, context: EvoContext
) -> AsyncGenerator[None, None]:
    """Acquire the route lock and set ``EvoContext`` for the scope."""
    lock = await get_thread_lock(thread_id)
    async with lock:
        token = ContextManager.set(context)
        try:
            yield
        finally:
            ContextManager.reset(token)
