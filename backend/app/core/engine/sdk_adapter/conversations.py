"""Per-thread OpenHands Conversation registry.

Caching the conversation avoids the biggest integration round-trip: rebuilding
the Agent + re-reading the full EventLog from disk on every delivery. The
cached conversation lives as long as the thread does; ``reset_conversation_store``
(rewind / conversation deletion) evicts it so the next turn replays DB history.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CachedConversation:
    conversation: Any
    tool_names: set[str] = field(default_factory=set)
    last_token: str = ""


_CACHE: dict[str, CachedConversation] = {}
_LOCK = threading.RLock()


def get_cached(thread_id: str) -> CachedConversation | None:
    with _LOCK:
        return _CACHE.get(thread_id)


def put_cached(thread_id: str, entry: CachedConversation) -> None:
    with _LOCK:
        _CACHE[thread_id] = entry


def pop_cached(thread_id: str) -> CachedConversation | None:
    with _LOCK:
        return _CACHE.pop(thread_id, None)
