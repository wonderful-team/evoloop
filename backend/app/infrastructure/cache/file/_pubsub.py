"""
In-memory Pub/Sub adapter for FileCache.
"""

import asyncio
from queue import Empty
from typing import Any

from app.infrastructure.cache.abstract import PubSubBackend
from app.utils.pubsub import in_memory_bus


class InMemoryPubSubAdapter(PubSubBackend):
    def __init__(self):
        self._subscriptions: dict[str, Any] = {}

    async def subscribe(self, *channels: str) -> None:
        for channel in channels:
            if channel not in self._subscriptions:
                self._subscriptions[channel] = in_memory_bus.subscribe(channel)

    async def unsubscribe(self, *channels: str) -> None:
        for channel in channels:
            if channel in self._subscriptions:
                in_memory_bus.unsubscribe(channel, self._subscriptions[channel])
                del self._subscriptions[channel]

    async def get_message(self, ignore_subscribe_messages: bool = False, timeout: float | None = None) -> dict | None:
        if not self._subscriptions:
            return None
        channel = next(iter(self._subscriptions.keys()))
        queue = self._subscriptions[channel]

        if timeout:
            import time
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    msg = queue.get_nowait()
                    return {"type": "message", "channel": channel, "data": msg}
                except Empty:
                    await asyncio.sleep(0.01)
            return None
        else:
            try:
                msg = queue.get_nowait()
                return {"type": "message", "channel": channel, "data": msg}
            except Empty:
                return None

    async def close(self) -> None:
        for channel, queue in list(self._subscriptions.items()):
            in_memory_bus.unsubscribe(channel, queue)
        self._subscriptions.clear()
