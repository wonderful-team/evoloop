"""Unit coverage for the skills file watcher."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.learning.skills import watcher as watcher_module
from app.core.learning.skills.watcher import SkillsFileWatcher


class TestFilters:
    def test_is_skill_md(self):
        assert watcher_module._is_skill_md("/x/SKILL.md") is True
        assert watcher_module._is_skill_md("/x/notes.txt") is False

    def test_is_skill_relevant_skill_md(self):
        assert watcher_module._is_skill_relevant("/x/SKILL.md") is True

    def test_is_skill_relevant_extensionless_dir(self):
        assert watcher_module._is_skill_relevant("/x/my-skill") is True

    def test_is_skill_relevant_noise(self):
        assert watcher_module._is_skill_relevant("/x/notes.txt") is False


@pytest.fixture
def fake_sync_service(monkeypatch):
    svc = SimpleNamespace(
        import_skill_from_disk=AsyncMock(),
        delete_skill_by_path=AsyncMock(),
    )
    monkeypatch.setattr(watcher_module, "skill_sync_service", svc)
    return svc


@pytest.mark.asyncio
class TestFileHandlers:
    async def test_created_imports(self, fake_sync_service):
        event = SimpleNamespace(data={"path": "/skills/os/SKILL.md"})
        await watcher_module._handle_file_created(event)
        fake_sync_service.import_skill_from_disk.assert_awaited_once_with(
            "/skills/os/SKILL.md"
        )

    async def test_created_ignores_non_skill(self, fake_sync_service):
        await watcher_module._handle_file_created(
            SimpleNamespace(data={"path": "/skills/os/notes.txt"})
        )
        fake_sync_service.import_skill_from_disk.assert_not_awaited()

    async def test_modified_imports(self, fake_sync_service, tmp_path):
        md = tmp_path / "SKILL.md"
        md.write_text("x")
        event = SimpleNamespace(data={"path": str(md)})
        await watcher_module._handle_file_modified(event)
        fake_sync_service.import_skill_from_disk.assert_awaited_once_with(str(md))

    async def test_modified_skips_missing(self, fake_sync_service, tmp_path):
        await watcher_module._handle_file_modified(
            SimpleNamespace(data={"path": str(tmp_path / "gone.md")})
        )
        fake_sync_service.import_skill_from_disk.assert_not_awaited()

    async def test_deleted_calls_delete(self, fake_sync_service):
        await watcher_module._handle_file_deleted(
            SimpleNamespace(data={"path": "/skills/os/SKILL.md"})
        )
        fake_sync_service.delete_skill_by_path.assert_awaited_once_with(
            "/skills/os/SKILL.md"
        )

    async def test_deleted_ignores_non_skill(self, fake_sync_service):
        await watcher_module._handle_file_deleted(
            SimpleNamespace(data={"path": "/skills/os/notes.txt"})
        )
        fake_sync_service.delete_skill_by_path.assert_not_awaited()

    async def test_directory_deleted(self, fake_sync_service):
        await watcher_module._handle_directory_deleted(
            SimpleNamespace(data={"path": "/skills/os"})
        )
        fake_sync_service.delete_skill_by_path.assert_awaited_once_with(
            "/skills/os/SKILL.md"
        )


class TestWatcherLifecycle:
    def test_start_skips_missing_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            watcher_module,
            "settings",
            SimpleNamespace(SKILLS_DIR=str(tmp_path / "nope")),
        )
        w = SkillsFileWatcher()
        w.start()
        assert not w.is_running

    def test_start_stop_with_fake_file_watcher(self, tmp_path, monkeypatch):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        monkeypatch.setattr(
            watcher_module, "settings", SimpleNamespace(SKILLS_DIR=str(skills_dir))
        )

        fake = SimpleNamespace(is_running=False, start=lambda: None, stop=lambda: None)
        monkeypatch.setattr(watcher_module, "FileWatcher", lambda **kw: fake)

        bus = SimpleNamespace(
            subscribe=lambda *a, **k: None, unsubscribe=lambda *a, **k: None
        )
        monkeypatch.setattr("app.core.events.system_bus", bus)

        w = SkillsFileWatcher()
        w.start()
        assert w._watcher is fake
        # second start is a no-op while already watching
        w.start()
        assert w._subscribed is True
        w.stop()
        assert w._watcher is None
