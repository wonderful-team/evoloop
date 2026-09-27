"""Integration tests for the stream routes (app/api/routes/stream.py).

The SSE endpoints produce an endless stream. We patch the route-module
``get_message_broker`` and ``activity_monitor`` with stubs whose fake pub/sub
raises ``StopAsyncIteration`` once messages are exhausted, which terminates the
event generator so httpx can read the full response.
"""

from __future__ import annotations

import json
from types import SimpleNamespace


class _FakePubSub:
    """In-memory pub/sub stub that yields canned messages then exits."""

    def __init__(self, messages=None):
        self._messages = messages or []
        self._index = 0

    async def subscribe(self, channel):
        pass

    async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
        if self._index >= len(self._messages):
            raise StopAsyncIteration
        msg = self._messages[self._index]
        self._index += 1
        return msg

    async def close(self):
        pass


class _FakeBroker:
    def __init__(self, messages=None):
        self._messages = messages or []

    def pubsub(self):
        return _FakePubSub(self._messages)


def _patch_broker(monkeypatch, messages=None):
    monkeypatch.setattr(
        "app.api.routes.stream.get_message_broker",
        lambda: _FakeBroker(messages),
    )


async def _no_activity(_thread_id):
    return None


def _patch_broker_and_no_activity(monkeypatch, messages=None):
    _patch_broker(monkeypatch, messages)
    monkeypatch.setattr(
        "app.api.routes.stream.activity_monitor",
        SimpleNamespace(get_activity=_no_activity),
    )


class TestStreamChat:
    async def test_returns_sse_stream(self, client, monkeypatch):
        _patch_broker_and_no_activity(monkeypatch)
        resp = await client.get("/stream/chat/thread-1")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    async def test_sends_activity_snapshot(self, client, monkeypatch):
        snapshot = SimpleNamespace(
            model_dump=lambda: {"status": "idle", "human_request": None},
            status="idle",
            human_request=None,
        )

        async def _get_activity(_tid):
            return snapshot

        _patch_broker(monkeypatch)
        monkeypatch.setattr(
            "app.api.routes.stream.activity_monitor",
            SimpleNamespace(get_activity=_get_activity),
        )

        resp = await client.get("/stream/chat/t-1")
        assert resp.status_code == 200
        body = resp.text
        assert "event: activity" in body
        assert "idle" in body

    async def test_sends_human_request_event(self, client, monkeypatch):
        snapshot = SimpleNamespace(
            model_dump=lambda: {
                "status": "idle",
                "human_request": {"question": "Approve?", "options": ["y", "n"]},
            },
            status="idle",
            human_request={"question": "Approve?", "options": ["y", "n"]},
        )

        async def _get_activity(_tid):
            return snapshot

        _patch_broker(monkeypatch)
        monkeypatch.setattr(
            "app.api.routes.stream.activity_monitor",
            SimpleNamespace(get_activity=_get_activity),
        )

        resp = await client.get("/stream/chat/t-2")
        assert resp.status_code == 200
        body = resp.text
        assert "event: human_request" in body
        assert "Approve?" in body

    async def test_forwards_pubsub_messages(self, client, monkeypatch):
        event = {"type": "token", "text": "hello"}
        messages = [
            {"type": "message", "data": json.dumps(event)},
        ]
        _patch_broker_and_no_activity(monkeypatch, messages)
        resp = await client.get("/stream/chat/t-3")
        assert resp.status_code == 200
        body = resp.text
        assert "event: token" in body
        assert "hello" in body


class TestStreamSystem:
    async def test_returns_sse_stream(self, client, monkeypatch):
        _patch_broker(monkeypatch)
        resp = await client.get("/stream/system")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    async def test_forwards_system_events(self, client, monkeypatch):
        event = {"type": "indexing.status", "status": "running"}
        messages = [{"type": "message", "data": json.dumps(event)}]
        _patch_broker(monkeypatch, messages)
        resp = await client.get("/stream/system")
        assert resp.status_code == 200
        body = resp.text
        assert "indexing.status" in body
