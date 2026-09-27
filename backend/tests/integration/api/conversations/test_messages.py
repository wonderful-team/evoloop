"""Integration tests for conversations/messages.py routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest  # noqa: F401


@pytest.fixture(autouse=True)
def _mock_session_scope(monkeypatch):
    @asynccontextmanager
    async def _fake_scope():
        yield SimpleNamespace()

    monkeypatch.setattr(
        "app.api.routes.conversations.messages.session_scope", _fake_scope
    )


def _empty_scalars():
    return SimpleNamespace(all=lambda: [])


def _empty_session():
    async def _execute(_stmt):
        return SimpleNamespace(scalars=_empty_scalars)

    return SimpleNamespace(execute=_execute)


def _noop_normalize(messages):
    return messages


class TestGetConversationMessages:
    async def test_empty_messages(self, client, monkeypatch):
        async def _get_full_history(**_kwargs):
            return [], False, 0

        monkeypatch.setattr(
            "app.api.routes.conversations.messages.MessageRepository",
            lambda thread_id: SimpleNamespace(get_full_history=_get_full_history),
        )
        monkeypatch.setattr(
            "app.api.routes.conversations.messages.MessageNormalizer",
            SimpleNamespace(normalize=_noop_normalize),
        )
        monkeypatch.setattr(
            "app.api.routes.conversations.messages.session_scope",
            lambda: _ctx(_empty_session()),
        )
        resp = await client.get("/conversations/t-1/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_more"] is False
        assert data["data"] == []

    async def test_messages_with_tool_calls_stripped(self, client, monkeypatch):
        from app.core.engine.message.schemas import (
            MessageBlock,
            MessageContentType,
            MessageRole,
        )

        msg = MessageBlock(
            id="m-1",
            thread_id="t-1",
            role=MessageRole.AI,
            content="hello",
            content_type=MessageContentType.TEXT,
            references=[],
            tool_calls=None,
        )

        async def _get_full_history(**_kwargs):
            return [msg], False, 1

        monkeypatch.setattr(
            "app.api.routes.conversations.messages.MessageRepository",
            lambda thread_id: SimpleNamespace(get_full_history=_get_full_history),
        )
        monkeypatch.setattr(
            "app.api.routes.conversations.messages.MessageNormalizer",
            SimpleNamespace(normalize=_noop_normalize),
        )
        monkeypatch.setattr(
            "app.api.routes.conversations.messages.session_scope",
            lambda: _ctx(_empty_session()),
        )
        resp = await client.get("/conversations/t-1/messages?include_tool_calls=false")
        assert resp.status_code == 200
        assert resp.json()["data"][0]["tool_calls"] is None

    async def test_tool_role_content_cleared(self, client, monkeypatch):
        from app.core.engine.message.schemas import (
            MessageBlock,
            MessageContentType,
            MessageRole,
        )

        msg = MessageBlock(
            id="m-2",
            thread_id="t-1",
            role=MessageRole.TOOL,
            content="secret-output",
            content_type=MessageContentType.TEXT,
            references=[],
            tool_calls=None,
        )

        async def _get_full_history(**_kwargs):
            return [msg], False, 1

        monkeypatch.setattr(
            "app.api.routes.conversations.messages.MessageRepository",
            lambda thread_id: SimpleNamespace(get_full_history=_get_full_history),
        )
        monkeypatch.setattr(
            "app.api.routes.conversations.messages.MessageNormalizer",
            SimpleNamespace(normalize=_noop_normalize),
        )
        monkeypatch.setattr(
            "app.api.routes.conversations.messages.session_scope",
            lambda: _ctx(_empty_session()),
        )
        resp = await client.get("/conversations/t-1/messages")
        assert resp.status_code == 200
        assert resp.json()["data"][0]["content"] == ""


class TestSearchConversations:
    async def test_empty_query(self, client, monkeypatch):
        resp = await client.get("/conversations/search?q=a")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_short_query(self, client, monkeypatch):
        resp = await client.get("/conversations/search?q=a")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_search_results(self, client, monkeypatch):
        msg = SimpleNamespace(
            id="m-1",
            thread_id="t-1",
            role="user",
            content="hello world",
            created_at="2024-01-01T00:00:00",
        )

        class _Exec:
            def scalars(self_inner):
                return SimpleNamespace(all=lambda: [msg])

        async def _exec(_stmt):
            return _Exec()

        monkeypatch.setattr(
            "app.api.routes.conversations.messages.session_scope",
            lambda: _ctx(SimpleNamespace(execute=_exec)),
        )
        resp = await client.get("/conversations/search?q=hello+world")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["thread_id"] == "t-1"
        assert data[0]["match_snippet"] == "hello world"


class TestRewindConversation:
    async def test_rewind_success(self, client, monkeypatch):
        result = SimpleNamespace(
            status="rewound",
            removed_message_count=3,
            reverted_file_count=1,
        )

        async def _perform_rewind(**_kwargs):
            return result

        monkeypatch.setattr(
            "app.core.engine.rewind.perform_rewind",
            _perform_rewind,
        )
        resp = await client.post(
            "/conversations/t-1/rewind",
            json={"revert_files": True, "message_id": "m-target"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rewound"
        assert data["removed_count"] == 3

    async def test_rewind_empty(self, client, monkeypatch):
        result = SimpleNamespace(status="empty")

        async def _perform_rewind(**_kwargs):
            return result

        monkeypatch.setattr(
            "app.core.engine.rewind.perform_rewind",
            _perform_rewind,
        )
        resp = await client.post("/conversations/t-1/rewind")
        assert resp.status_code == 200
        assert resp.json()["status"] == "empty"

    async def test_rewind_no_human_message(self, client, monkeypatch):
        result = SimpleNamespace(status="no_human_message_found")

        async def _perform_rewind(**_kwargs):
            return result

        monkeypatch.setattr(
            "app.core.engine.rewind.perform_rewind",
            _perform_rewind,
        )
        resp = await client.post("/conversations/t-1/rewind")
        assert resp.status_code == 200
        assert resp.json()["status"] == "no_human_message_found"

    async def test_rewind_target_not_found(self, client, monkeypatch):
        from app.core.engine.rewind import MessageNotFoundError

        async def _perform_rewind(**_kwargs):
            raise MessageNotFoundError("target not found")

        monkeypatch.setattr(
            "app.core.engine.rewind.perform_rewind",
            _perform_rewind,
        )
        resp = await client.post("/conversations/t-1/rewind")
        assert resp.status_code == 404

    async def test_rewind_partial_failure_is_not_reported_as_rewound(
        self, client, monkeypatch
    ):
        result = SimpleNamespace(
            status="partial_failure",
            removed_message_count=3,
            reverted_file_count=0,
            errors=["file rewind failed"],
        )

        async def _perform_rewind(**_kwargs):
            return result

        monkeypatch.setattr(
            "app.core.engine.rewind.perform_rewind",
            _perform_rewind,
        )
        resp = await client.post(
            "/conversations/t-1/rewind",
            json={"revert_files": True, "message_id": "m-target"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "partial_failure"
        assert data["removed_count"] == 3
        assert data["errors"] == ["file rewind failed"]


class TestGetThreadChangeset:
    async def test_empty_changeset(self, client, monkeypatch):
        class _Exec:
            def scalars(self_inner):
                return SimpleNamespace(all=lambda: [])

        async def _exec(_stmt):
            return _Exec()

        monkeypatch.setattr(
            "app.api.routes.conversations.messages.session_scope",
            lambda: _ctx(SimpleNamespace(execute=_exec)),
        )
        resp = await client.get("/conversations/t-1/changeset")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_changeset_with_files(self, client, monkeypatch):
        ops = [
            SimpleNamespace(
                file_path="main.py",
                operation="ADD",
                diff_content="+added",
                created_at="2024-01-01T00:00:00",
            ),
        ]

        class _Exec:
            def scalars(self_inner):
                return SimpleNamespace(all=lambda: ops)

        async def _exec(_stmt):
            return _Exec()

        monkeypatch.setattr(
            "app.api.routes.conversations.messages.session_scope",
            lambda: _ctx(SimpleNamespace(execute=_exec)),
        )
        resp = await client.get("/conversations/t-1/changeset")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "main.py"
        assert data[0]["is_dir"] is False
        assert data[0]["operation"] == "ADD"


# ---------- helpers ----------


class AsyncStub:
    def __init__(self, return_value):
        self._value = return_value

    async def __call__(self, *args, **kwargs):
        return self._value


@asynccontextmanager
async def _ctx(session):
    yield session
