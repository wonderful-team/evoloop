"""Integration tests for projects/profiles.py routes."""

from __future__ import annotations

from types import SimpleNamespace

import pytest  # noqa: F401


@pytest.fixture(autouse=True)
def _mock_check_benefit(monkeypatch):
    monkeypatch.setattr("app.api.deps.check_benefit", AsyncStub(True))


class TestDiscoverProfile:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.profiles.get_project_path",
            AsyncStub("/ws/proj"),
        )
        monkeypatch.setattr("os.path.isdir", lambda p: True)
        monkeypatch.setattr(
            "app.api.routes.projects.profiles.dispatch_agent_run",
            AsyncStub(
                SimpleNamespace(
                    status="success",
                    inputs={"thread_id": "t-discovery"},
                )
            ),
        )
        monkeypatch.setattr(
            "app.api.routes.projects.profiles.run_agent_background", lambda *a: None
        )
        monkeypatch.setattr(
            "app.core.context.thread_context_store",
            SimpleNamespace(set_working_directory=lambda *a: None),
        )
        monkeypatch.setattr(
            "app.api.routes.projects.profiles._ensure_project_discovery_skill",
            AsyncStub(None),
        )
        resp = await client.post(
            "/projects/1/profile/discover",
            json={"record_secrets": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["project_id"] == 1

    async def test_project_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.profiles.get_project_path",
            AsyncStub(None),
        )
        resp = await client.post(
            "/projects/999/profile/discover",
            json={"record_secrets": False},
        )
        assert resp.status_code == 404

    async def test_path_not_directory(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.profiles.get_project_path",
            AsyncStub("/ws/proj"),
        )
        monkeypatch.setattr("os.path.isdir", lambda p: False)
        resp = await client.post(
            "/projects/1/profile/discover",
            json={"record_secrets": False},
        )
        assert resp.status_code == 400


class TestGetProfile:
    async def test_exists(self, client, monkeypatch, tmp_path):
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        (proj_dir / "PROJECT.md").write_text("# Hello")
        (proj_dir / ".evoloop").mkdir()
        (proj_dir / ".evoloop" / "project.json").write_text('{"name": "proj"}')

        monkeypatch.setattr(
            "app.api.routes.projects.profiles.get_project_path",
            AsyncStub(str(proj_dir)),
        )
        resp = await client.get("/projects/1/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True
        assert data["name"] == "proj"

    async def test_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.profiles.get_project_path",
            AsyncStub(None),
        )
        resp = await client.get("/projects/999/profile")
        assert resp.status_code == 404

    async def test_no_project_md(self, client, monkeypatch, tmp_path):
        proj_dir = tmp_path / "empty"
        proj_dir.mkdir()
        (proj_dir / ".evoloop").mkdir()
        (proj_dir / ".evoloop" / "project.json").write_text("{}")

        monkeypatch.setattr(
            "app.api.routes.projects.profiles.get_project_path",
            AsyncStub(str(proj_dir)),
        )
        resp = await client.get("/projects/1/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is False
        assert data["content"] is None


class TestUpdateProfile:
    async def test_success(self, client, monkeypatch, tmp_path):
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        (proj_dir / ".evoloop").mkdir()
        (proj_dir / ".evoloop" / "project.json").write_text("{}")

        monkeypatch.setattr(
            "app.api.routes.projects.profiles.get_project_path",
            AsyncStub(str(proj_dir)),
        )
        monkeypatch.setattr(
            "app.api.routes.projects.profiles.file_utils",
            SimpleNamespace(
                write_file=lambda path, content: None,
                read_file=lambda path: SimpleNamespace(content="# Updated"),
            ),
        )
        monkeypatch.setattr(
            "app.api.routes.projects.profiles.read_project_json",
            lambda path: {"name": "proj", "url": None, "framework_profile": None},
        )
        monkeypatch.setattr(
            "app.api.routes.projects.profiles.write_project_json",
            lambda path, data: None,
        )

        resp = await client.patch(
            "/projects/1/profile",
            json={"content": "# Updated", "name": "proj"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True

    async def test_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.profiles.get_project_path",
            AsyncStub(None),
        )
        resp = await client.patch(
            "/projects/999/profile",
            json={"content": "# x"},
        )
        assert resp.status_code == 404


class TestGetProjectSettings:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.profiles.get_project_path",
            AsyncStub("/ws/proj"),
        )
        monkeypatch.setattr(
            "app.api.routes.projects.profiles.read_project_json",
            lambda path: {"name": "my-proj", "url": "https://example.com"},
        )
        resp = await client.get("/projects/1/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "my-proj"
        assert data["url"] == "https://example.com"

    async def test_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.profiles.get_project_path",
            AsyncStub(None),
        )
        resp = await client.get("/projects/999/settings")
        assert resp.status_code == 404


class TestUpdateProjectSettings:
    async def test_success(self, client, monkeypatch):
        saved = {}

        monkeypatch.setattr(
            "app.api.routes.projects.profiles.get_project_path",
            AsyncStub("/ws/proj"),
        )

        def _write(_path, data):
            saved.update(data)

        def _read(_path):
            return {"name": saved.get("name"), "url": saved.get("url")}

        monkeypatch.setattr(
            "app.api.routes.projects.profiles.write_project_json", _write
        )
        monkeypatch.setattr(
            "app.api.routes.projects.profiles.read_project_json", _read
        )
        resp = await client.patch(
            "/projects/1/settings",
            json={"name": "new-name", "url": "https://new.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "new-name"
        assert data["url"] == "https://new.com"

    async def test_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.projects.profiles.get_project_path",
            AsyncStub(None),
        )
        resp = await client.patch(
            "/projects/999/settings",
            json={"name": "x"},
        )
        assert resp.status_code == 404


# ---------- helpers ----------


class AsyncStub:
    def __init__(self, return_value):
        self._value = return_value

    async def __call__(self, *args, **kwargs):  # noqa: ARG002
        return self._value
