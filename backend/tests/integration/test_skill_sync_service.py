"""Coverage for SkillSyncService (DB ↔ filesystem sync coordination)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete

from app.core.learning import synthesizer_utils as synth_utils
from app.core.learning.skills import discovery as discovery_module
from app.core.learning.skills import sync_service as sync_module
from app.core.learning.skills.sync_service import skill_sync_service
from app.models.learning import LearnedSkill


def _skill(name: str, **kw) -> LearnedSkill:
    defaults = {
        "name": name,
        "description": f"desc {name}",
        "trigger_patterns": [name],
        "parameters": [],
        "namespace": None,
        "status": "verified",
        "is_active": True,
    }
    defaults.update(kw)
    return LearnedSkill(**defaults)


@pytest.fixture(autouse=True)
def _clean_skills(test_session_scope):
    yield

    async def _clean():
        async with test_session_scope() as db:
            await db.execute(delete(LearnedSkill))

    asyncio.run(_clean())


@pytest.fixture
def sync_env(test_session_scope, tmp_path, monkeypatch):
    skills_dir = str(tmp_path / "skills")
    monkeypatch.setattr(sync_module, "session_scope", test_session_scope)
    monkeypatch.setattr(sync_module, "settings", SimpleNamespace(SKILLS_DIR=skills_dir))
    monkeypatch.setattr(synth_utils, "settings", SimpleNamespace(SKILLS_DIR=skills_dir))
    monkeypatch.setattr(discovery_module.skill_discovery, "reload", AsyncMock())
    return tmp_path


@pytest.mark.asyncio
class TestExportToFile:
    async def test_exports_and_sets_resource_path(self, sync_env, test_session_scope, tmp_path):
        async with test_session_scope() as db:
            s = _skill(
                "exp", namespace="os/macos", instructions="Do the thing."
            )
            db.add(s)
            await db.flush()
            sid = s.id

        path = await skill_sync_service.export_skill_to_file(sid)
        assert path is not None
        md = tmp_path / "skills" / "os" / "macos" / "exp" / "SKILL.md"
        assert md.exists()
        assert "name: exp" in md.read_text(encoding="utf-8")

        async with test_session_scope() as db:
            row = await db.get(LearnedSkill, sid)
            assert row.resource_path == str(md.parent)

    async def test_missing_skill(self, sync_env):
        assert await skill_sync_service.export_skill_to_file(999_999) is None


@pytest.mark.asyncio
class TestDeleteSkillFile:
    async def test_deletes_by_namespace_and_name(self, sync_env, tmp_path):
        target = tmp_path / "skills" / "os" / "macos" / "del"
        target.mkdir(parents=True)
        ok = await skill_sync_service.delete_skill_file(
            1, namespace="os/macos", name="del"
        )
        assert ok is True
        assert not target.exists()

    async def test_falls_back_to_db_lookup(self, sync_env, test_session_scope, tmp_path):
        target = tmp_path / "skills" / "os" / "del"
        target.mkdir(parents=True)
        async with test_session_scope() as db:
            s = _skill("del", namespace="os")
            db.add(s)
            await db.flush()
            sid = s.id
        ok = await skill_sync_service.delete_skill_file(sid)
        assert ok is True
        assert not target.exists()

    async def test_missing(self, sync_env):
        assert await skill_sync_service.delete_skill_file(999_999) is False


@pytest.mark.asyncio
class TestImportFromDisk:
    async def test_imports_and_reloads(self, sync_env, tmp_path, monkeypatch):
        md = tmp_path / "skills" / "os" / "macos" / "click" / "SKILL.md"
        md.parent.mkdir(parents=True)
        md.write_text("---\nname: click\ndescription: c\n---\n", encoding="utf-8")

        imp = AsyncMock(return_value=True)
        monkeypatch.setattr(sync_module.SkillImporter, "import_single_skill", imp)

        ok = await skill_sync_service.import_skill_from_disk(str(md))
        assert ok is True
        imp.assert_awaited_once()
        discovery_module.skill_discovery.reload.assert_awaited_once()

    async def test_import_failure(self, sync_env, tmp_path, monkeypatch):
        md = tmp_path / "skills" / "x" / "SKILL.md"
        md.parent.mkdir(parents=True)
        md.write_text("---\n", encoding="utf-8")
        monkeypatch.setattr(
            sync_module.SkillImporter, "import_single_skill", AsyncMock(return_value=False)
        )
        ok = await skill_sync_service.import_skill_from_disk(str(md))
        assert ok is False


@pytest.mark.asyncio
class TestDeleteByPath:
    async def test_deletes_db_row_and_publishes(self, sync_env, test_session_scope, tmp_path, monkeypatch):
        folder = tmp_path / "skills" / "os" / "macos" / "gone"
        folder.mkdir(parents=True)
        async with test_session_scope() as db:
            s = _skill("gone", namespace="os/macos")
            db.add(s)
            await db.flush()
            sid = s.id

        from app.core.events import publishers

        pub = AsyncMock()
        monkeypatch.setattr(publishers, "publish_skill_mutated", pub)

        ok = await skill_sync_service.delete_skill_by_path(str(folder / "SKILL.md"))
        assert ok is True
        pub.assert_awaited_once()
        discovery_module.skill_discovery.reload.assert_awaited_once()

        async with test_session_scope() as db:
            assert await db.get(LearnedSkill, sid) is None

    async def test_no_matching_row(self, sync_env, tmp_path):
        folder = tmp_path / "skills" / "os" / "nope"
        folder.mkdir(parents=True)
        ok = await skill_sync_service.delete_skill_by_path(str(folder / "SKILL.md"))
        assert ok is False
