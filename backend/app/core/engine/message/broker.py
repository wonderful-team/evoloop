"""
MessageBroker — Unified message publishing and subscription abstraction.

Replaces the obsolete EventBus naming to eliminate process-wide event bus confusion.
"""

import json
import logging
from abc import ABC, abstractmethod
from collections import OrderedDict, deque
from typing import Any

from redis.exceptions import RedisError

from app.infrastructure.cache.abstract import PubSubBackend
from app.utils.pubsub import in_memory_bus

logger = logging.getLogger(__name__)


class EventReplayBuffer:
    """Per-thread SSE 事件环形缓冲（新线程竞态/断线重连的回放层）。

    问题：POST /chat 在响应返回前就启动 run，前端要等响应回来才建立 SSE
    订阅——首条消息早期事件（token/status）丢失；EventSource 自动重连同理。
    方案：publish 时按 thread 记录最近 N 条事件；SSE 连接按 SSE 原生
    Last-Event-ID（前端 EventSource 自动回传）断点续传，首次连接全量回放。

    线程数上限 FIFO 淘汰；分布式部署下多进程各持本进程缓冲（SSE 与
    publish 同进程时回放有效，跨进程退化为现状行为——如需跨进程应挂
    Redis list，当前 Embedded 部署单进程即完整生效）。
    """

    MAX_EVENTS_PER_THREAD = 500
    MAX_THREADS = 200

    def __init__(self) -> None:
        # thread_id -> deque[(seq, raw_json_str)]，OrderedDict 维护插入序供淘汰
        self._buffers: OrderedDict[str, deque] = OrderedDict()
        self._seqs: dict[str, int] = {}

    @staticmethod
    def thread_id_of(channel: str) -> str | None:
        # channel 形如 chat:{thread_id}:events、workflow:{workflow_id}:events、
        # tasks:{project_id}:events、thread:{thread_id}:events、system:events
        prefix = next(
            (
                prefix
                for prefix in ("chat:", "workflow:", "tasks:", "thread:", "system:")
                if channel.startswith(prefix)
            ),
            None,
        )
        if prefix and channel.endswith(":events"):
            tid = channel[len(prefix):-7]
            return tid or None
        return None

    def record(self, channel: str, raw_data: str) -> int:
        tid = self.thread_id_of(channel)
        if tid is None:
            return 0
        buf = self._buffers.get(tid)
        if buf is None:
            buf = deque(maxlen=self.MAX_EVENTS_PER_THREAD)
            self._buffers[tid] = buf
            self._seqs.setdefault(tid, 0)
            self._evict_old()
        self._seqs[tid] += 1
        buf.append((self._seqs[tid], raw_data))
        return self._seqs[tid]

    def snapshot_since(self, thread_id: str, last_seq: int | None) -> list[tuple[int, str]]:
        buf = self._buffers.get(thread_id)
        if not buf:
            return []
        start = last_seq if last_seq is not None else 0
        return [(s, raw) for (s, raw) in buf if s > start]

    def current_seq(self, thread_id: str) -> int:
        return self._seqs.get(thread_id, 0)

    def _evict_old(self) -> None:
        while len(self._buffers) > self.MAX_THREADS:
            oldest, _ = self._buffers.popitem(last=False)
            self._seqs.pop(oldest, None)


event_replay_buffer = EventReplayBuffer()


class MessageBroker(ABC):
    """Abstract message broker for publishing and subscribing to real-time events/messages."""

    @abstractmethod
    async def publish(self, channel: str, message: Any) -> int:
        """Publish a message to a channel. Returns number of subscribers notified."""
        ...

    @abstractmethod
    def pubsub(self) -> PubSubBackend:
        """Return a PubSub adapter for subscription."""
        ...


class LocalMessageBroker(MessageBroker):
    """
    In-process message broker for single-process deployments (Embedded Mode).
    Uses thread-safe local SimplePubSubBus.
    """

    async def publish(self, channel: str, message: Any) -> int:
        try:
            raw = message if isinstance(message, str) else json.dumps(message, default=str)
            seq = event_replay_buffer.record(channel, raw)
            # chat channel 包装 seq 供 SSE 实时事件标注 id:
            #（Last-Event-ID 断点续传需要每条事件都有序号）
            out = (
                json.dumps({"_evt_seq": seq, "_evt_raw": raw})
                if seq
                else message
            )
            in_memory_bus.publish(channel, out)
            return 1
        except (RuntimeError, TypeError, AttributeError) as e:
            logger.warning(f"[LocalMessageBroker] Publish failed: {e}", exc_info=True)
            return 0

    def pubsub(self) -> PubSubBackend:
        from app.infrastructure.cache.file.pubsub import InMemoryPubSubAdapter

        return InMemoryPubSubAdapter()


class DistributedMessageBroker(MessageBroker):
    """
    Cross-process message broker for distributed deployments (Production Mode).
    Uses a centralized message broker (Redis) via cache infrastructure.
    """

    async def publish(self, channel: str, message: Any) -> int:
        try:
            raw = message if isinstance(message, str) else json.dumps(message, default=str)
            seq = event_replay_buffer.record(channel, raw)
            out = (
                json.dumps({"_evt_seq": seq, "_evt_raw": raw})
                if seq
                else message
            )
            from app.infrastructure.cache import cache

            return await cache.publish(channel, out)
        except (RedisError, OSError, TypeError, ValueError) as e:
            logger.exception(
                f"[DistributedMessageBroker] Publish failed to channel {channel}: {e}"
            )
            return 0

    def pubsub(self) -> PubSubBackend:
        from app.infrastructure.cache import cache

        return cache.pubsub()


# Global singleton instance
_message_broker: MessageBroker | None = None


def get_message_broker() -> MessageBroker:
    """
    Get the global message broker instance.

    Selects implementation based on settings.EMBEDDED_MODE.
    """
    global _message_broker
    if _message_broker is None:
        from app.core.config import settings

        if settings.EMBEDDED_MODE:
            logger.info(
                "[MessageBroker] Initializing LocalMessageBroker (Embedded Mode)"
            )
            _message_broker = LocalMessageBroker()
        else:
            logger.info(
                "[MessageBroker] Initializing DistributedMessageBroker (Production Mode)"
            )
            _message_broker = DistributedMessageBroker()

    return _message_broker
