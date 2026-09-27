"""Integration tests for the planning routes (app/api/routes/planning.py)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _mock_session_scope(monkeypatch):
    @asynccontextmanager
    async def _fake_scope():
        session = SimpleNamespace(
            execute=_make_execute(first=None, all_items=[]),
        )
        yield session

    monkeypatch.setattr(
        "app.api.routes.planning.session_scope", _fake_scope
    )


def _make_execute(first, all_items):
    async def _execute(_stmt):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(
                first=lambda: first,
                all=lambda: all_items,
            )
        )

    return _execute


class TestGetPlan:
    async def test_no_plan(self, client):
        resp = await client.get("/planning/conversations/t-1/plan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "no_plan"
        assert data["plan"] is None

    async def test_has_plan(self, client, monkeypatch):
        plan = SimpleNamespace(
            id="p1",
            title="My Plan",
            status="active",
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        step1 = SimpleNamespace(
            id="s1", title="Step 1", status="in_progress", result=None, order=0
        )
        step2 = SimpleNamespace(
            id="s2", title="Step 2", status="pending", result=None, order=1
        )

        @asynccontextmanager
        async def _scope_with_plan():
            session = SimpleNamespace(
                execute=_make_execute(first=plan, all_items=[step1, step2]),
            )
            yield session

        monkeypatch.setattr(
            "app.api.routes.planning.session_scope", _scope_with_plan
        )
        resp = await client.get("/planning/conversations/t-1/plan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["plan"]["id"] == "p1"
        assert data["plan"]["title"] == "My Plan"
        assert len(data["plan"]["steps"]) == 2
        assert data["plan"]["current_step_id"] == "s1"

    async def test_exception_returns_error(self, client, monkeypatch):
        @asynccontextmanager
        async def _scope_error():
            raise RuntimeError("db down")
            yield  # pragma: no cover

        monkeypatch.setattr(
            "app.api.routes.planning.session_scope", _scope_error
        )
        resp = await client.get("/planning/conversations/t-1/plan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "db down" in data["error"]
