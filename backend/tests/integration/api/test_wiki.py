"""Integration tests for the wiki routes (app/api/routes/wiki.py)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


async def _async_return(value):
    return value


async def _no_value():
    return None


async def test_get_wiki_pages_empty(client, monkeypatch):
    from app.domain.wiki.service import wiki_service

    monkeypatch.setattr(wiki_service, "get_pages", lambda pid, member_id=None: [])
    resp = await client.get("/wiki/1")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_wiki_pages_with_data(client, monkeypatch):
    from app.domain.wiki.service import wiki_service

    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    page = SimpleNamespace(
        id=1,
        project_id=1,
        title="Overview",
        slug="overview",
        content="# Overview",
        parent_id=None,
        order=0,
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(
        wiki_service, "get_pages", lambda pid, member_id=None: [page]
    )
    resp = await client.get("/wiki/1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Overview"


class TestGenerateWiki:
    @pytest.fixture(autouse=True)
    def _allow_benefit(self, monkeypatch):
        import app.api.deps as deps

        async def _check(_benefit_code, _token):
            return True

        monkeypatch.setattr(deps, "check_benefit", _check)

    async def test_project_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.wiki.get_project_path",
            lambda pid: _async_return(None),
        )
        resp = await client.post(
            "/wiki/generate",
            json={"project_id": 999, "topic": "Docs"},
        )
        assert resp.status_code == 404

    async def test_success(self, client, monkeypatch):
        from app.core.engine.dispatch import DispatchStatus

        monkeypatch.setattr(
            "app.api.routes.wiki.get_project_path",
            lambda pid: _async_return("/tmp/proj"),
        )
        monkeypatch.setattr("os.path.isdir", lambda p: True)
        monkeypatch.setattr("app.api.routes.wiki.unique_id", lambda *a: "thread-1")

        result = SimpleNamespace(
            status=DispatchStatus.QUEUED,
            inputs={"thread_id": "t-1"},
            error=None,
        )
        monkeypatch.setattr(
            "app.api.routes.wiki.dispatch_agent_run",
            lambda **kw: _async_return(result),
        )
        monkeypatch.setattr(
            "app.api.routes.wiki._ensure_wiki_generation_skill",
            _no_value,
        )
        monkeypatch.setattr(
            "app.api.routes.wiki.SystemConfigService.get_language_preference",
            lambda: "en",
        )
        monkeypatch.setattr(
            "app.api.routes.wiki.run_agent_background",
            lambda *a, **k: None,
        )
        from app.i18n.service import i18n

        monkeypatch.setattr(i18n, "get", lambda k: k)

        resp = await client.post(
            "/wiki/generate",
            json={"project_id": 1, "topic": "Project Docs"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["task_id"] == "thread-1"

    async def test_dispatch_failure(self, client, monkeypatch):
        from app.core.engine.dispatch import DispatchStatus

        monkeypatch.setattr(
            "app.api.routes.wiki.get_project_path",
            lambda pid: _async_return("/tmp/proj"),
        )
        monkeypatch.setattr("os.path.isdir", lambda p: True)
        monkeypatch.setattr("app.api.routes.wiki.unique_id", lambda *a: "t-1")

        result = SimpleNamespace(
            status=DispatchStatus.FAILED, inputs={}, error="boom"
        )
        monkeypatch.setattr(
            "app.api.routes.wiki.dispatch_agent_run",
            lambda **kw: _async_return(result),
        )
        monkeypatch.setattr(
            "app.api.routes.wiki._ensure_wiki_generation_skill",
            _no_value,
        )
        monkeypatch.setattr(
            "app.api.routes.wiki.SystemConfigService.get_language_preference",
            lambda: "en",
        )

        resp = await client.post(
            "/wiki/generate",
            json={"project_id": 1, "topic": "X"},
        )
        assert resp.status_code == 500
