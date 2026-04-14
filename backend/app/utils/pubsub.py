import asyncio
from collections import defaultdict
from typing import Any

class SimplePubSubBus:
    """A global in-process bus for message broadcasting when cache is not available."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SimplePubSubBus, cls).__new__(cls)
            cls._instance.subscribers = defaultdict(list)
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    async def subscribe(self, channel: str) -> asyncio.Queue:
        async with self._lock:
            queue = asyncio.Queue()
            self.subscribers[channel].append(queue)
            return queue

    async def unsubscribe(self, channel: str, queue: asyncio.Queue):
        async with self._lock:
            if channel in self.subscribers:
                if queue in self.subscribers[channel]:
                    self.subscribers[channel].remove(queue)
                if not self.subscribers[channel]:
                    del self.subscribers[channel]

    async def publish(self, channel: str, message: Any):
        async with self._lock:
            queues = list(self.subscribers.get(channel, []))
        
        for queue in queues:
            await queue.put(message)

# Global Instance
in_memory_bus = SimplePubSubBus()
