"""Integration tests for /webhook agent route (app/api/routes/agent/webhook.py)."""

from __future__ import annotations

from types import SimpleNamespace


def _adapt_result():
    return [
        SimpleNamespace(role="user", content="incoming event"),
    ]


async def _dispatch(*_args, **kwargs):
    return SimpleNamespace(
        status="queued",
        thread_id=kwargs.get("thread_id"),
        message_id="m1",
        inputs={"goal": "x"},
        error=None,
    )


class TestWebhookValidation:
    async def test_webhook_missing_fields_422(self, client):
        resp = await client.post("/webhook", json={})
        assert resp.status_code == 422

    async def test_webhook_missing_event_type_422(self, client):
        resp = await client.post("/webhook", json={"source": "gitlab"})
        assert resp.status_code == 422

    async def test_webhook_missing_payload_422(self, client):
        resp = await client.post(
            "/webhook", json={"source": "gitlab", "event_type": "issue"}
        )
        assert resp.status_code == 422


class TestWebhookAccepted:
    async def test_webhook_accepts_valid_event(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.agent.webhook.EventAdapter.adapt",
            lambda source, event_type, payload: _adapt_result(),
        )
        monkeypatch.setattr(
            "app.api.routes.agent.webhook.dispatch_agent_run", _dispatch
        )
        monkeypatch.setattr(
            "app.api.routes.agent.webhook.run_agent_background", lambda *a, **k: None
        )
        resp = await client.post(
            "/webhook",
            json={
                "source": "gitlab",
                "event_type": "issue",
                "thread_id": "t1",
                "payload": {"id": "e1", "text": "hello"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["thread_id"] == "t1"

    async def test_webhook_default_thread_id(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.agent.webhook.EventAdapter.adapt",
            lambda source, event_type, payload: _adapt_result(),
        )
        monkeypatch.setattr(
            "app.api.routes.agent.webhook.dispatch_agent_run", _dispatch
        )
        monkeypatch.setattr(
            "app.api.routes.agent.webhook.run_agent_background", lambda *a, **k: None
        )
        resp = await client.post(
            "/webhook",
            json={
                "source": "gitlab",
                "event_type": "issue",
                "payload": {"id": "e1"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["thread_id"] == "gitlab-e1"
