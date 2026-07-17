import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

lancedb = pytest.importorskip("lancedb")  # noqa: F401

from app.core.routing import sync  # noqa: E402
from app.core.routing.index import RouteIndex  # noqa: E402


def _vecs(n: int, dim: int = 8) -> list[list[float]]:
    return [[0.1 + j * 0.001 for j in range(dim)] for _ in range(n)]


class _FakeEmbedder:
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return _vecs(len(texts))

    async def embed_query(self, _text: str) -> list[float]:
        return _vecs(1)[0]


@pytest.mark.asyncio
async def test_rebuild_writes_local_and_agent(tmp_path, monkeypatch):
    idx = RouteIndex(str(tmp_path / "v"), dim=8)
    monkeypatch.setattr(sync, "_get_embedder", lambda: _FakeEmbedder())
    monkeypatch.setattr(sync, "get_index", lambda: idx)
    # Isolate from the real DB: no learned skills / domain nouns.
    monkeypatch.setattr(sync, "_skill_entries", lambda: [])

    async def _noop_domain_nouns():
        return []

    monkeypatch.setattr(sync, "_collect_domain_nouns", _noop_domain_nouns)

    written = await sync.rebuild_route_index()

    expected_locals = len({a["id"] for a in sync._VOICE_LOCAL_ACTIONS})
    assert written == expected_locals + 1  # + 1 agent entry
    assert idx.count() == written
    ids = {r["id"] for r in idx.list_entries(limit=100)}
    assert "local:play_pause" in ids
    assert "local:end" in ids
    assert "agent:default" in ids


@pytest.mark.asyncio
async def test_rebuild_no_embedder_returns_zero(tmp_path, monkeypatch):
    idx = RouteIndex(str(tmp_path / "v"), dim=8)
    monkeypatch.setattr(sync, "_get_embedder", lambda: None)
    monkeypatch.setattr(sync, "get_index", lambda: idx)

    assert await sync.rebuild_route_index() == 0
    assert idx.count() == 0


@pytest.mark.asyncio
async def test_delete_skill(tmp_path, monkeypatch):
    idx = RouteIndex(str(tmp_path / "v"), dim=8)
    idx.upsert(
        [
            {
                "id": "skill:42",
                "type": "skill",
                "name": "x",
                "description": "x",
                "params_schema": {},
                "target": "42",
            }
        ],
        _vecs(1),
    )
    assert idx.count() == 1
    monkeypatch.setattr(sync, "get_index", lambda: idx)

    assert await sync.delete_skill(42) is True
    assert idx.count() == 0


@pytest.mark.asyncio
async def test_upsert_skill_no_embedder_returns_false(monkeypatch):
    monkeypatch.setattr(sync, "_get_embedder", lambda: None)
    assert await sync.upsert_skill(42) is False


@pytest.mark.asyncio
async def test_on_skill_mutated_dispatch(monkeypatch):
    calls: list[tuple[str, int]] = []

    async def _upsert(skill_id: int) -> bool:
        calls.append(("upsert", skill_id))
        return True

    async def _delete(skill_id: int) -> bool:
        calls.append(("delete", skill_id))
        return True

    monkeypatch.setattr(sync, "upsert_skill", _upsert)
    monkeypatch.setattr(sync, "delete_skill", _delete)

    await sync.on_skill_mutated(7, "create")
    await sync.on_skill_mutated(7, "update")
    await sync.on_skill_mutated(7, "delete")

    assert calls == [("upsert", 7), ("upsert", 7), ("delete", 7)]


def _patch_sync_session(session, monkeypatch):
    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr(
        "app.infrastructure.database.sql.database.sync_session_scope",
        _scope,
    )


@pytest.mark.asyncio
async def test_upsert_skill_deletes_when_inactive_current_behavior(monkeypatch):
    session = MagicMock()
    session.get.return_value = MagicMock(is_active=False)
    delete = AsyncMock(return_value=True)
    monkeypatch.setattr(sync, "_get_embedder", lambda: _FakeEmbedder())
    monkeypatch.setattr(sync, "delete_skill", delete)
    _patch_sync_session(session, monkeypatch)

    assert await sync.upsert_skill(42) is True
    delete.assert_awaited_once_with(42)


@pytest.mark.asyncio
async def test_upsert_skill_pending_review_is_not_routable(monkeypatch):
    skill = MagicMock(
        is_active=True,
        status="pending_review",
        id=8,
        name="pending_skill",
        description="d",
        parameters="[]",
        execution_mode="deterministic",
    )
    session = MagicMock()
    session.get.return_value = skill
    index = MagicMock()
    delete = AsyncMock(return_value=True)
    monkeypatch.setattr(sync, "_get_embedder", lambda: _FakeEmbedder())
    monkeypatch.setattr(sync, "get_index", lambda: index)
    monkeypatch.setattr(sync, "delete_skill", delete)
    _patch_sync_session(session, monkeypatch)

    assert await sync.upsert_skill(8) is True
    delete.assert_awaited_once_with(8)
    index.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_skill_verified_active_is_routable(monkeypatch):
    skill = MagicMock(
        is_active=True,
        status="verified",
        id=9,
        name="verified_skill",
        description="d",
        parameters='[{"name": "q", "type": "string", "required": true}]',
        execution_mode="agentic",
    )
    session = MagicMock()
    session.get.return_value = skill
    index = MagicMock()
    index.upsert.return_value = 1
    monkeypatch.setattr(sync, "_get_embedder", lambda: _FakeEmbedder())
    monkeypatch.setattr(sync, "get_index", lambda: index)
    _patch_sync_session(session, monkeypatch)

    assert await sync.upsert_skill(9) is True
    entries, vectors = index.upsert.call_args[0]
    assert entries[0]["id"] == "skill:9"
    assert entries[0]["params_schema"] == {"q": {"type": "string", "required": True}}
    assert len(vectors) == 1


def test_skill_to_entry_parses_params_schema():
    params = json.dumps([{"name": "app", "type": "string", "required": True}])
    skill = SimpleNamespace(
        id=5,
        name="s",
        description="d",
        parameters=params,
        execution_mode="deterministic",
    )

    entry = sync._skill_to_entry(skill)

    assert entry["id"] == "skill:5"
    assert entry["params_schema"] == {"app": {"type": "string", "required": True}}


def test_skill_to_entry_unparseable_params_keep_raw():
    skill = SimpleNamespace(
        id=6,
        name="s",
        description="d",
        parameters="{not json",
        execution_mode="deterministic",
    )

    entry = sync._skill_to_entry(skill)

    assert entry["params_schema"] == {"raw": "{not json"}


def test_skill_entries_only_includes_verified_active():
    pending = SimpleNamespace(
        is_active=True,
        status="pending_review",
        id=8,
        name="pending_skill",
        description="d",
        parameters="[]",
        execution_mode="deterministic",
    )
    verified = SimpleNamespace(
        is_active=True,
        status="verified",
        id=9,
        name="verified_skill",
        description="d",
        parameters=json.dumps([{"name": "q", "type": "string"}]),
        execution_mode="agentic",
    )
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = [
        pending,
        verified,
    ]

    @contextmanager
    def _scope():
        yield session

    with patch("app.infrastructure.database.sql.database.sync_session_scope", _scope):
        entries = sync._skill_entries()

    assert [e["id"] for e in entries] == ["skill:9"]
    assert entries[0]["params_schema"] == {"q": {"type": "string"}}


def test_entry_embed_text_includes_trigger_phrases():
    """Users speak trigger phrases — they must be part of the embedded text."""
    s = SimpleNamespace(
        id=9,
        name="macos_dev_window_switching",
        description="Switch focus between dev apps",
        trigger_patterns=["在终端和 PyCharm 之间切换", "切换到 {{target_app}} 窗口"],
        parameters=None,
        execution_mode="deterministic",
    )

    entry = sync._skill_to_entry(s)
    text = sync._entry_embed_text(entry)

    assert "macos_dev_window_switching" in text
    assert "Switch focus between dev apps" in text
    assert "在终端和 PyCharm 之间切换" in text
    assert "切换到" in text
    assert "窗口" in text
    assert "{{target_app}}" not in text


def test_trigger_text_parses_json_string_and_bad_shapes():
    assert sync._trigger_text(SimpleNamespace(trigger_patterns='["a", "b"]')) == "a b"
    assert sync._trigger_text(SimpleNamespace(trigger_patterns="not json")) == ""
    assert sync._trigger_text(SimpleNamespace(trigger_patterns=None)) == ""
    assert sync._trigger_text(SimpleNamespace(trigger_patterns=42)) == ""
