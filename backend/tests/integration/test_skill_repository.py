"""Unit coverage for app.core.learning.skills.repository.

Runs against a throwaway SQLite DB (see tests/integration/conftest.py).
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.learning.skills import repository as repo_module
from app.models.learning import LearnedSkill


def _skill(name: str, *, member_id: int = 0, is_active: bool = True, status: str = "verified", **kw) -> LearnedSkill:
    defaults = {
        "name": name,
        "description": f"desc {name}",
        "trigger_patterns": [name],
        "parameters": [],
        "member_id": member_id,
        "is_active": is_active,
        "status": status,
    }
    defaults.update(kw)
    return LearnedSkill(**defaults)


@pytest.fixture(autouse=True)
def _clean_skills(test_session_scope):
    """The test DB is session-scoped and shared; wipe skills between tests."""
    from sqlalchemy import delete

    yield

    async def _clean():
        async with test_session_scope() as db:
            await db.execute(delete(LearnedSkill))

    asyncio.run(_clean())


@pytest.fixture
def repo_scope(test_session_scope, monkeypatch):
    """Point the repository's self-managed session_scope at the test DB."""
    monkeypatch.setattr(repo_module, "session_scope", test_session_scope)


@pytest.mark.asyncio
class TestGetById:
    async def test_found(self, repo_scope, test_session_scope):
        async with test_session_scope() as db:
            s = _skill("a")
            db.add(s)
            await db.flush()
            sid = s.id
        got = await repo_module.skill_repository.get_by_id(sid)
        assert got is not None and got.name == "a"

    async def test_missing(self, repo_scope):
        assert await repo_module.skill_repository.get_by_id(999_999) is None

    async def test_zero_id(self, repo_scope):
        assert await repo_module.skill_repository.get_by_id(0) is None

    async def test_visible_only_excludes_inactive(self, repo_scope, test_session_scope):
        async with test_session_scope() as db:
            hidden = _skill("hidden", is_active=False)
            db.add(hidden)
            await db.flush()
            hid = hidden.id
        assert await repo_module.skill_repository.get_by_id(hid, visible_only=True) is None
        assert await repo_module.skill_repository.get_by_id(hid) is not None

    async def test_member_scope(self, repo_scope, test_session_scope):
        async with test_session_scope() as db:
            sys_skill = _skill("sys", member_id=0)
            own_skill = _skill("own", member_id=7)
            other = _skill("other", member_id=9)
            db.add_all([sys_skill, own_skill, other])
            await db.flush()
            ids = {"sys": sys_skill.id, "own": own_skill.id, "other": other.id}
        # member scope = system(0) + own
        assert await repo_module.skill_repository.get_by_id(ids["sys"], member_id=7) is not None
        assert await repo_module.skill_repository.get_by_id(ids["own"], member_id=7) is not None
        assert await repo_module.skill_repository.get_by_id(ids["other"], member_id=7) is None
        # include_system=False → only own rows
        assert await repo_module.skill_repository.get_by_id(ids["sys"], member_id=7, include_system=False) is None
        assert await repo_module.skill_repository.get_by_id(ids["own"], member_id=7, include_system=False) is not None

    async def test_accepts_explicit_db(self, repo_scope, test_session_scope):
        async with test_session_scope() as db:
            s = _skill("attached")
            db.add(s)
            await db.flush()
            sid = s.id
            got = await repo_module.skill_repository.get_by_id(sid, db=db)
            assert got is not None and got.name == "attached"


@pytest.mark.asyncio
class TestGetByName:
    async def test_found(self, repo_scope, test_session_scope):
        async with test_session_scope() as db:
            db.add(_skill("exact"))
            await db.flush()
        assert await repo_module.skill_repository.get_by_name("exact") is not None
        assert await repo_module.skill_repository.get_by_name("missing") is None

    async def test_visible_only(self, repo_scope, test_session_scope):
        async with test_session_scope() as db:
            db.add(_skill("v", is_active=False))
            await db.flush()
        assert await repo_module.skill_repository.get_by_name("v", visible_only=True) is None
        assert await repo_module.skill_repository.get_by_name("v") is not None


@pytest.mark.asyncio
class TestGetByIds:
    async def test_batch(self, repo_scope, test_session_scope):
        async with test_session_scope() as db:
            a = _skill("a")
            b = _skill("b", is_active=False)
            db.add_all([a, b])
            await db.flush()
            ids = [a.id, b.id]
        rows = await repo_module.skill_repository.get_by_ids(ids)
        assert {r.name for r in rows} == {"a", "b"}
        # visible_only drops the inactive row
        rows_v = await repo_module.skill_repository.get_by_ids(ids, visible_only=True)
        assert {r.name for r in rows_v} == {"a"}

    async def test_empty(self, repo_scope):
        assert await repo_module.skill_repository.get_by_ids([]) == []


@pytest.mark.asyncio
class TestListPage:
    async def _seed(self, test_session_scope):
        async with test_session_scope() as db:
            db.add_all(
                [
                    _skill("sys1", member_id=0, status="verified", is_active=True),
                    _skill("sys2", member_id=0, status="pending_review", is_active=False),
                    _skill("own1", member_id=5, status="verified", is_active=True),
                    _skill("own2", member_id=5, status="verified", is_active=False),
                    _skill("other", member_id=9, status="verified", is_active=True),
                ]
            )
            await db.flush()

    async def test_pagination_and_total(self, repo_scope, test_session_scope):
        await self._seed(test_session_scope)
        # unscoped global list
        rows, total = await repo_module.skill_repository.list_page(1, 2, active_only=False)
        assert total == 5 and len(rows) == 2
        rows2, _ = await repo_module.skill_repository.list_page(3, 2, active_only=False)
        assert len(rows2) == 1

    async def test_member_scope(self, repo_scope, test_session_scope):
        await self._seed(test_session_scope)
        rows, total = await repo_module.skill_repository.list_page(
            1, 100, member_id=5, active_only=False
        )
        assert {r.name for r in rows} == {"sys1", "sys2", "own1", "own2"}
        assert total == 4

    async def test_active_only(self, repo_scope, test_session_scope):
        await self._seed(test_session_scope)
        _, total_all = await repo_module.skill_repository.list_page(1, 100, active_only=False)
        _, total_act = await repo_module.skill_repository.list_page(1, 100, active_only=True)
        assert total_all == 5 and total_act == 3

    async def test_page_floor(self, repo_scope, test_session_scope):
        await self._seed(test_session_scope)
        rows, _ = await repo_module.skill_repository.list_page(0, 100, active_only=False)
        assert len(rows) == 5


@pytest.mark.asyncio
class TestValidateIds:
    async def test_missing_subset(self, repo_scope, test_session_scope):
        async with test_session_scope() as db:
            a = _skill("a")
            db.add(a)
            await db.flush()
            aid = a.id
        missing = await repo_module.skill_repository.validate_ids([aid, 777, 888])
        assert missing == [777, 888]

    async def test_empty(self, repo_scope):
        assert await repo_module.skill_repository.validate_ids([]) == []
