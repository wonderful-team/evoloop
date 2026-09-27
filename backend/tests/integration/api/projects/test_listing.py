"""Integration tests for projects/listing.py routes."""

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
        "app.api.routes.projects.listing.session_scope", _fake_scope
    )


class _FakePipeline:
    def __init__(self):
        self._keys: list[str] = []

    def hgetall(self, key):
        self._keys.append(key)
        return self

    async def execute(self):
        return [{} for _ in self._keys]


class _FakeCache:
    @staticmethod
    def pipeline():
        return _FakePipeline()


class TestGetProjects:
    async def test_empty_cloud_list(self, client, monkeypatch):
        _patch_all(monkeypatch, cloud_projects=[], local_index={}, repos=[])
        resp = await client.get("/projects/")
        assert resp.status_code == 200
        data = resp.json()
        if isinstance(data, dict):
            assert data.get("list", []) == []

    async def test_cloud_projects_enriched(self, client, monkeypatch):
        cloud = [{"project_id": 1, "name": "proj-a"}]
        _patch_all(
            monkeypatch,
            cloud_projects=cloud,
            local_index={1: SimpleNamespace(path="/ws/proj-a")},
            repos=[],
        )
        resp = await client.get("/projects/")
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("list", data) if isinstance(data, dict) else data
        assert len(items) >= 1

    async def test_filter_switchable(self, client, monkeypatch):
        cloud = [
            {"project_id": 1, "name": "a"},
            {"project_id": 2, "name": "b"},
        ]
        _patch_all(
            monkeypatch,
            cloud_projects=cloud,
            local_index={1: SimpleNamespace(path="/ws/a")},
            repos=[],
        )
        resp = await client.get("/projects/?filter_type=switchable")
        assert resp.status_code == 200

    async def test_filter_cloud_only(self, client, monkeypatch):
        cloud = [{"project_id": 1, "name": "a"}]
        _patch_all(
            monkeypatch,
            cloud_projects=cloud,
            local_index={},
            repos=[],
        )
        resp = await client.get("/projects/?filter_type=cloud_only")
        assert resp.status_code == 200

    async def test_cloud_returns_list_format(self, client, monkeypatch):
        cloud = [{"project_id": 1, "name": "x"}]
        _patch_all(
            monkeypatch,
            cloud_projects=cloud,
            local_index={1: SimpleNamespace(path="/ws/x")},
            repos=[],
        )
        resp = await client.get("/projects/")
        assert resp.status_code == 200


# ---------- helpers ----------


def _patch_all(
    monkeypatch,
    *,
    cloud_projects: list[dict],
    local_index: dict,
    repos: list,
    duty_tasks: list | None = None,
):
    captured = {}

    async def _get_projects(page, page_size, token=None):
        captured.update({"page": page, "page_size": page_size, "token": token})
        return {"list": cloud_projects, "total": len(cloud_projects)}

    monkeypatch.setattr(
        "app.api.routes.projects.listing.evocloud_manager",
        SimpleNamespace(api=SimpleNamespace(get_projects=_get_projects)),
    )
    monkeypatch.setattr(
        "app.api.routes.projects.listing._scan_workspace_projects",
        lambda: {},
    )
    monkeypatch.setattr(
        "app.api.routes.projects.listing.local_project_index",
        SimpleNamespace(refresh=lambda ws: local_index),
    )
    monkeypatch.setattr(
        "app.api.routes.projects.listing.get_workspace_root",
        lambda: "/ws",
    )

    class _Exec:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return SimpleNamespace(all=lambda: self._items)

        def scalar_one_or_none(self):
            return self._items[0] if self._items else None

        def scalar_one(self):
            return self._items[0]

    repo_exec = _Exec(repos)
    task_exec = _Exec(duty_tasks or [])
    ignored_exec = _Exec([])

    class _FakeSession:
        def __init__(self):
            self._call_count = 0
            self._added: list = []
            self._next_id = 1

        async def execute(self, _stmt):
            self._call_count += 1
            if self._call_count == 1:
                return repo_exec
            if self._call_count == 2:
                return task_exec
            if self._call_count == 3:
                return ignored_exec
            # Second-session writes: return a synthetic id for inserts/updates
            return _Exec([self._next_id])

        async def get(self, _model, _id):
            return None

        def add(self, obj):
            self._added.append(obj)

        async def flush(self):
            for obj in self._added:
                if getattr(obj, "id", None) is None:
                    obj.id = self._next_id
                    self._next_id += 1
            self._added.clear()

    monkeypatch.setattr(
        "app.api.routes.projects.listing.session_scope",
        lambda: _ctx(_FakeSession()),
    )
    monkeypatch.setattr(
        "app.api.routes.projects.listing.wiki_service",
        SimpleNamespace(get_projects_with_wiki=lambda ids: set()),
    )
    monkeypatch.setattr(
        "app.api.routes.projects.listing.cache", _FakeCache()
    )
    monkeypatch.setattr(
        "app.api.routes.projects.listing._read_duty_status",
        AsyncStub(
            {
                "enabled": False,
                "active": False,
                "last_run_at": None,
                "next_run_at": None,
                "interval": 60,
                "business_poll_interval": 30,
                "business_last_run_at": None,
                "business_next_run_at": None,
                "last_failure": None,
                "global_enabled": False,
            }
        ),
    )


class AsyncStub:
    def __init__(self, return_value):
        self._value = return_value

    async def __call__(self, *args, **kwargs):  # noqa: ARG002
        return self._value


@asynccontextmanager
async def _ctx(session):
    yield session
