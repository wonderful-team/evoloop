import threading
from collections import defaultdict
from queue import Full, Queue
from typing import Any


class SimplePubSubBus:
    """
    A global in-process bus for message broadcasting.

    Thread-safe using threading.Lock and standard library Queue.
    Works across asyncio event loops (e.g. Huey worker threads
    vs. main FastAPI thread).
    """

    _instance = None
    _init_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.subscribers = defaultdict(list)
                    cls._instance._lock = threading.Lock()
        return cls._instance

    def subscribe(self, channel: str) -> Queue:
        """Subscribe to a channel. Returns a thread-safe Queue."""
        with self._lock:
            queue: Queue = Queue(maxsize=10000)
            self.subscribers[channel].append(queue)
            return queue

    def unsubscribe(self, channel: str, queue: Queue):
        """Unsubscribe a queue from a channel."""
        with self._lock:
            if channel in self.subscribers:
                if queue in self.subscribers[channel]:
                    self.subscribers[channel].remove(queue)
                if not self.subscribers[channel]:
                    del self.subscribers[channel]

    def publish(self, channel: str, message: Any):
        """Publish a message to all subscribers of a channel."""
        with self._lock:
            queues = list(self.subscribers.get(channel, []))

        for queue in queues:
            try:
                queue.put_nowait(message)
            except Full:
                # Drop oldest message to make room
                try:
                    queue.get_nowait()
                    queue.put_nowait(message)
                except (TypeError, ValueError, RuntimeError):
                    pass


# Global Instance
in_memory_bus = SimplePubSubBus()
