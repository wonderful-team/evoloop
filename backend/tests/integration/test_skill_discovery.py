"""Coverage for SkillDiscovery (agent-runtime read path)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete

from app.core.learning.skills import discovery as discovery_module
from app.core.learning.skills.discovery import SkillDiscovery
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


class _FakeConfig:
    @staticmethod
    def get_value(key, default=None):
        return "true"

    @staticmethod
    def set_value(*args, **kwargs):
        return SimpleNamespace()


@pytest.fixture(autouse=True)
def _clean_skills(test_session_scope):
    yield

    async def _clean():
        async with test_session_scope() as db:
            await db.execute(delete(LearnedSkill))

    asyncio.run(_clean())


@pytest.fixture
def discovery(test_session_scope, monkeypatch):
    monkeypatch.setattr(discovery_module, "session_scope", test_session_scope)
    monkeypatch.setattr(discovery_module, "SystemConfigService", _FakeConfig)
    return SkillDiscovery()


@pytest.mark.asyncio
class TestGetSkillById:
    async def test_found(self, discovery, test_session_scope):
        async with test_session_scope() as db:
            s = _skill("demo")
            db.add(s)
            await db.flush()
            sid = s.id
        got = await discovery.get_skill_by_id(sid)
        assert got is not None and got.name == "demo"

    async def test_missing(self, discovery):
        assert await discovery.get_skill_by_id(999_999) is None

    async def test_zero(self, discovery):
        assert await discovery.get_skill_by_id(0) is None

    async def test_inactive_not_in_cache(self, discovery, test_session_scope):
        async with test_session_scope() as db:
            s = _skill("hidden", is_active=False)
            db.add(s)
            await db.flush()
            sid = s.id
        # discovery only indexes active skills
        assert await discovery.get_skill_by_id(sid) is None


@pytest.mark.asyncio
class TestExactSearch:
    async def test_by_id(self, discovery, test_session_scope):
        async with test_session_scope() as db:
            s = _skill("demo")
            db.add(s)
            await db.flush()
            sid = s.id
        match, relevant, _ = await discovery.exact_search(str(sid))
        assert match is not None and match.skill_id == sid
        assert relevant and relevant[0].id == sid

    async def test_by_name(self, discovery, test_session_scope):
        async with test_session_scope() as db:
            db.add(_skill("demo"))
            await db.flush()
        match, _, _ = await discovery.exact_search("demo")
        assert match is not None and match.skill_name == "demo"

    async def test_namespace_prefix(self, discovery, test_session_scope):
        async with test_session_scope() as db:
            db.add(_skill("os/macos/click", namespace="os/macos"))
            await db.flush()
        # query is a name-prefix, not an exact name → falls to prefix branch
        match, _, _ = await discovery.exact_search("os/macos/cli")
        assert match is not None and match.skill_name == "os/macos/click"

    async def test_no_match(self, discovery):
        match, relevant, _ = await discovery.exact_search("nope")
        assert match is None and relevant == []

    async def test_empty_query(self, discovery):
        match, relevant, reason = await discovery.exact_search("")
        assert match is None and relevant == []
        assert reason != ""


@pytest.mark.asyncio
class TestCatalog:
    async def test_catalog_and_namespace_filter(self, discovery, test_session_scope):
        async with test_session_scope() as db:
            db.add_all(
                [
                    _skill("a", namespace="os/macos"),
                    _skill("b", namespace="os/android"),
                ]
            )
            await db.flush()
        index = await discovery.get_skills_catalog(namespace="os/macos")
        assert [x["name"] for x in index] == ["a"]

    async def test_catalog_query(self, discovery, test_session_scope):
        async with test_session_scope() as db:
            db.add_all([_skill("alpha"), _skill("beta")])
            await db.flush()
        index = await discovery.get_skills_catalog(query="alph")
        assert [x["name"] for x in index] == ["alpha"]

    async def test_namespace_index(self, discovery, test_session_scope):
        async with test_session_scope() as db:
            db.add(_skill("c", namespace="os/macos"))
            await db.flush()
        idx = await discovery.get_namespace_index("os/macos")
        assert idx and idx[0]["name"] == "c"

    async def test_active_skills_list(self, discovery, test_session_scope):
        async with test_session_scope() as db:
            db.add_all([_skill("x", is_active=True), _skill("y", is_active=False)])
            await db.flush()
        items = await discovery.get_active_skills_list()
        assert [i.name for i in items] == ["x"]

    async def test_reload_refreshes_cache(self, discovery, test_session_scope):
        async with test_session_scope() as db:
            db.add(_skill("first"))
            await db.flush()
        await discovery.get_active_skills_list()
        async with test_session_scope() as db:
            db.add(_skill("second"))
            await db.flush()
        # without reload, cache still holds only "first"
        assert [i.name for i in await discovery.get_active_skills_list()] == ["first"]
        await discovery.reload()
        assert {i.name for i in await discovery.get_active_skills_list()} == {
            "first",
            "second",
        }


@pytest.mark.asyncio
class TestEnsureSystemSkillsSynced:
    async def test_already_synced_flag(self, discovery, monkeypatch):
        # 清单一致 = 已同步 → 不重跑
        monkeypatch.setattr(
            discovery, "builtin_skills_manifest", lambda: "manifest-current"
        )
        config = SimpleNamespace(
            get_value=lambda key, default=None: "manifest-current",
            set_value=lambda *a, **k: None,
        )
        monkeypatch.setattr(discovery_module, "SystemConfigService", config)
        import_called = []
        monkeypatch.setattr(
            discovery_module.SkillImporter,
            "import_from_directory",
            AsyncMock(side_effect=lambda path: import_called.append(path)),
        )
        await discovery.ensure_system_skills_synced()
        assert import_called == []
        assert discovery._system_skills_synced is True

    async def test_legacy_true_flag_upgrades_to_resync(self, discovery, monkeypatch):
        """一次性 "true" 标志（老部署）必须触发一次增量重同步，并改写为清单。"""
        monkeypatch.setattr(
            discovery, "builtin_skills_manifest", lambda: "manifest-new"
        )
        set_calls = []
        config = SimpleNamespace(
            get_value=lambda key, default=None: "true",
            set_value=lambda *a, **k: set_calls.append(a),
        )
        monkeypatch.setattr(discovery_module, "SystemConfigService", config)
        import_called = []
        monkeypatch.setattr(
            discovery_module.SkillImporter,
            "import_from_directory",
            AsyncMock(side_effect=lambda path: import_called.append(path)),
        )
        await discovery.ensure_system_skills_synced()
        assert set_calls and set_calls[0][1] == "manifest-new"
        assert discovery._system_skills_synced is True

    async def test_syncs_when_unset(self, tmp_path, monkeypatch):
        calls = []
        set_calls = []

        class _Config:
            @staticmethod
            def get_value(key, default=None):
                return None

            @staticmethod
            def set_value(*args, **kwargs):
                set_calls.append((args, kwargs))
                return SimpleNamespace()

        monkeypatch.setattr(discovery_module, "SystemConfigService", _Config)
        monkeypatch.setattr(
            discovery_module,
            "settings",
            SimpleNamespace(SKILLS_DIR=str(tmp_path / "skills")),
        )
        importer = AsyncMock(side_effect=lambda path: calls.append(path))
        monkeypatch.setattr(
            discovery_module.SkillImporter, "import_from_directory", importer
        )

        d = SkillDiscovery()
        await d.ensure_system_skills_synced()
        # builtin skills copied to the tmp skills dir, then imported
        assert calls and str(tmp_path / "skills") in calls[0]
        assert set_calls
        assert d._system_skills_synced is True
        # second call is a no-op
        await d.ensure_system_skills_synced()
        assert len(calls) == 1
