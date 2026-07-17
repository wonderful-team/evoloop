"""Protocol resilience on reconnect / disconnect (design §14.7 protocol row, §14.6.7).

- A `voice.route_result` pushed to a thread with no live connection is dropped
  (returns False), never raised — so a client that disconnects after `routed`
  cannot crash the backend.
- A pushed-to-but-broken socket is swallowed (returns False), not leaked.
- A replayed `message_id` after a reconnect is de-duplicated across connections
  (idempotency is keyed by `message_id`, independent of the WS session).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.routing import idempotency
from app.core.routing.connection import VoiceConnectionManager


@pytest.mark.unit
@pytest.mark.asyncio
async def test_push_to_unknown_thread_drops_cleanly() -> None:
    mgr = VoiceConnectionManager()

    ok = await mgr.push("no-such-thread", {"type": "voice.route_result"})

    assert ok is False  # dropped, not raised


@pytest.mark.unit
@pytest.mark.asyncio
async def test_push_to_broken_socket_returns_false() -> None:
    mgr = VoiceConnectionManager()
    broken_ws = SimpleNamespace(send_json=AsyncMock(side_effect=OSError("socket closed")))
    await mgr.register("c1", broken_ws)
    await mgr.bind_thread("t1", "c1")

    ok = await mgr.push("t1", {"type": "voice.route_result"})

    assert ok is False  # send failed but was swallowed, not raised


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reconnect_replay_is_deduplicated(monkeypatch) -> None:
    monkeypatch.setattr(idempotency, "_seen", {})
    mgr = VoiceConnectionManager()

    # first connection sends message mid
    await mgr.register("c1", SimpleNamespace(send_json=AsyncMock()))
    assert await idempotency.is_duplicate("mid", ttl=60) is False  # first sight

    # client disconnects, reconnects as a NEW connection, resends same message_id
    await mgr.unregister("c1")
    await mgr.register("c2", SimpleNamespace(send_json=AsyncMock()))

    assert await idempotency.is_duplicate("mid", ttl=60) is True  # replay deduped
