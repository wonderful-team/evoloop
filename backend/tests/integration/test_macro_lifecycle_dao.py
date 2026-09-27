"""Full coverage of the macro lifecycle DAOs (query/create/update/delete/obsolete).

Runs against a throwaway SQLite DB (see tests/integration/conftest.py).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.core.learning.macro import lifecycle
from app.models.macro import Macro

VALID_SCRIPT = "steps:\n  - type: action\n    event_type: click\n"


def _build(status: str = "pending_review", is_active: bool = False, **kw) -> Macro:
    defaults = {
        "name": "m",
        "description": "",
        "trigger_patterns": [],
        "parameters": [],
        "macro_script": VALID_SCRIPT,
        "status": status,
        "is_active": is_active,
    }
    defaults.update(kw)
    return Macro(**defaults)


@pytest.fixture(autouse=True)
def _clean_macros(test_session_scope):
    """The test DB is session-scoped and shared; wipe macros between tests."""
    import asyncio

    from sqlalchemy import delete

    yield

    async def _clean():
        async with test_session_scope() as db:
            await db.execute(delete(Macro))

    asyncio.run(_clean())


@pytest.fixture
def lifecycle_scope(test_session_scope, monkeypatch):
    monkeypatch.setattr(lifecycle, "session_scope", test_session_scope)
    publish = AsyncMock()
    monkeypatch.setattr(lifecycle, "publish_macro_mutated", publish)
    return publish


@pytest.mark.asyncio
class TestLoad:
    async def test_load_macro_found(self, test_session_scope, lifecycle_scope):
        async with test_session_scope() as db:
            m = _build(status="verified", is_active=True, name="found")
            db.add(m)
            await db.flush()
            mid = m.id
        loaded = await lifecycle.load_macro(mid)
        assert loaded is not None and loaded.name == "found"
        # macro cache was removed (load_macro reads the DB every call):
        # successive loads return equal but not identical instances
        again = await lifecycle.load_macro(mid)
        assert again is not None and again.id == loaded.id and again.name == "found"

    async def test_load_macro_missing(self, test_session_scope, lifecycle_scope):
        assert await lifecycle.load_macro(999_999) is None

    async def test_load_verified_only_verified(self, test_session_scope, lifecycle_scope):
        async with test_session_scope() as db:
            v = _build(status="verified", is_active=True, name="v")
            p = _build(status="pending_review", is_active=False, name="p")
            db.add_all([v, p])
            await db.flush()
            vid, pid = v.id, p.id
        assert await lifecycle.load_verified_macro(vid) is not None
        assert await lifecycle.load_verified_macro(pid) is None


@pytest.mark.asyncio
class TestQuery:
    async def test_list_by_status(self, test_session_scope, lifecycle_scope):
        async with test_session_scope() as db:
            db.add_all(
                [
                    _build(status="verified", is_active=True, name="a"),
                    _build(status="pending_review", name="b"),
                    _build(status="obsolete", name="c"),
                ]
            )
            await db.flush()
        verified = await lifecycle.list_macros(status="verified")
        assert len(verified) == 1 and verified[0].name == "a"
        all_m = await lifecycle.list_macros()
        assert len(all_m) == 3

    async def test_find_by_name(self, test_session_scope, lifecycle_scope):
        async with test_session_scope() as db:
            db.add(_build(status="verified", is_active=True, name="unique-macro"))
            await db.flush()
        assert (await lifecycle.find_macro_by_name("unique-macro")) is not None
        assert (await lifecycle.find_macro_by_name("nope")) is None

    async def test_list_multi_keyword_ranking(self, test_session_scope, lifecycle_scope):
        async with test_session_scope() as db:
            db.add_all(
                [
                    _build(status="verified", is_active=True, name="打开商品 发布", description="发布商品"),
                    _build(status="verified", is_active=True, name="商品 编辑", description="打开商品管理"),
                ]
            )
            await db.flush()
        rows = await lifecycle.list_macros(status="verified", query="商品 打开")
        # the macro whose name contains the first keyword ranks first
        assert rows[0].name == "打开商品 发布"

    async def test_macro_to_yaml(self, test_session_scope, lifecycle_scope):
        from types import SimpleNamespace

        candidate = SimpleNamespace(
            macro_script=[
                {"type": "action", "event_type": "click", "payload": {"x": 1, "y": 2}}
            ]
        )
        yaml_str = lifecycle.macro_to_yaml(candidate)
        assert "steps:" in yaml_str


@pytest.mark.asyncio
class TestUpdate:
    async def test_update_allowed_fields(self, test_session_scope, lifecycle_scope):
        async with test_session_scope() as db:
            m = _build()
            db.add(m)
            await db.flush()
            mid = m.id
        ok = await lifecycle.update_macro(
            mid, {"name": "new", "trigger_patterns": ["x"], "risk_tier": "data"}
        )
        assert ok is True
        lifecycle_scope.assert_awaited_once_with(mid, action="update")
        async with test_session_scope() as db:
            updated = await db.get(Macro, mid)
            assert updated.name == "new"
            assert updated.trigger_patterns == ["x"]
            assert updated.risk_tier == "data"

    async def test_update_ignores_unknown_fields(self, test_session_scope, lifecycle_scope):
        async with test_session_scope() as db:
            m = _build()
            db.add(m)
            await db.flush()
            mid = m.id
        await lifecycle.update_macro(mid, {"status": "verified", "is_active": True})
        async with test_session_scope() as db:
            updated = await db.get(Macro, mid)
            # status/is_active are NOT in the whitelist → unchanged
            assert updated.status == "pending_review"
            assert updated.is_active is False

    async def test_update_missing(self, test_session_scope, lifecycle_scope):
        assert await lifecycle.update_macro(999_999, {"name": "x"}) is False


@pytest.mark.asyncio
class TestDeleteAndObsolete:
    async def test_delete(self, test_session_scope, lifecycle_scope):
        async with test_session_scope() as db:
            m = _build()
            db.add(m)
            await db.flush()
            mid = m.id
        assert await lifecycle.delete_macro(mid) is True
        lifecycle_scope.assert_awaited_once_with(mid, action="delete")
        async with test_session_scope() as db:
            assert await db.get(Macro, mid) is None

    async def test_delete_missing(self, test_session_scope, lifecycle_scope):
        assert await lifecycle.delete_macro(999_999) is False

    async def test_mark_obsolete_by_app_map(self, test_session_scope, lifecycle_scope):
        async with test_session_scope() as db:
            m1 = _build(status="verified", is_active=True, app_map_id=7)
            m2 = _build(status="verified", is_active=True, app_map_id=7)
            other = _build(status="verified", is_active=True, app_map_id=8)
            db.add_all([m1, m2, other])
            await db.flush()
            ids = [m1.id, m2.id]
        count = await lifecycle.mark_obsolete_by_app_map(7)
        assert count == 2
        async with test_session_scope() as db:
            rows = await db.get(Macro, ids[0])
            assert rows.status == "obsolete" and rows.is_active is False
        for mid in ids:
            lifecycle_scope.assert_any_await(mid, action="obsolete")



@pytest.mark.asyncio
class TestCreateSynthesis:
    async def test_creates_pending_review(self, test_session_scope, lifecycle_scope):
        async with test_session_scope() as db:
            macro = await lifecycle.create_macro_from_synthesis(
                db, name="syn", macro_script=VALID_SCRIPT, member_id=1
            )
            await db.flush()
            assert macro.id is not None
            assert macro.status == "pending_review"
            assert macro.is_active is False
            assert macro.app_map_id is None

    async def test_name_deduplicated(self, test_session_scope, lifecycle_scope):
        async with test_session_scope() as db:
            await lifecycle.create_macro_from_synthesis(db, name="dup", macro_script=VALID_SCRIPT)
            await db.flush()
            second = await lifecycle.create_macro_from_synthesis(
                db, name="dup", macro_script=VALID_SCRIPT
            )
            await db.flush()
            assert second.name == "dup_1"

    async def test_list_project_zero_semantics(self, test_session_scope, lifecycle_scope):
        async with test_session_scope() as db:
            db.add_all(
                [
                    _build(name="p0", project_id=0),
                    _build(name="pnull", project_id=None),
                    _build(name="p5", project_id=5),
                ]
            )
            await db.flush()
        rows = await lifecycle.list_macros(project_id=0)
        names = {m.name for m in rows}
        assert names == {"p0", "pnull"}


@pytest.mark.asyncio
class TestLifecycleMore:
    async def test_list_active_index(self, test_session_scope, lifecycle_scope):
        async with test_session_scope() as db:
            db.add_all(
                [
                    _build(name="act", status="verified", is_active=True),
                    _build(name="inact", status="verified", is_active=False),
                ]
            )
            await db.flush()
        idx = await lifecycle.list_active_macro_index()
        names = {m["name"] for m in idx}
        assert names == {"act"}

    async def test_persist_native_batch_replace(self, test_session_scope, lifecycle_scope):
        from types import SimpleNamespace

        candidates = [
            SimpleNamespace(
                name="App 打开",
                description="d",
                trigger_patterns=[],
                parameters=[],
                risk_tier="ui",
                requires_confirmation=False,
                steps=[{"type": "action", "event_type": "open_app", "payload": {}}],
            )
        ]
        ids = await lifecycle.persist_native_macros(
            candidates, project_id=1, member_id=0, namespace="native_macos"
        )
        assert len(ids) == 1
        # second run replaces, not duplicates
        await lifecycle.persist_native_macros(
            candidates, project_id=1, member_id=0, namespace="native_macos"
        )
        async with test_session_scope() as db:
            rows = (
                await db.execute(select(Macro).where(Macro.namespace == "native_macos"))
            ).scalars().all()
            assert len(rows) == 1

    async def test_find_by_name_with_project(self, test_session_scope, lifecycle_scope):
        async with test_session_scope() as db:
            db.add_all(
                [
                    _build(name="pm", project_id=1),
                    _build(name="pm", project_id=2),
                ]
            )
            await db.flush()
        assert (await lifecycle.find_macro_by_name("pm", project_id=1)) is not None
        assert (await lifecycle.find_macro_by_name("pm", project_id=99)) is None

    async def test_invalidate_cache(self, test_session_scope, lifecycle_scope):
        async with test_session_scope() as db:
            m = _build(name="cached")
            db.add(m)
            await db.flush()
            mid = m.id
        first = await lifecycle.load_macro(mid)
        assert first is not None
        # macro cache was removed; invalidate_macro_cache is kept as a
        # no-op for call-site compatibility and must not raise
        lifecycle.invalidate_macro_cache(mid)
        again = await lifecycle.load_macro(mid)
        assert again is not None and again.id == mid
