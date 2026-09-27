"""Integration tests for the AppMap data layer (persistence).

Covers save_app_map lifecycle (create / content-unchanged short-circuit /
version bump on change). Runs against the throwaway SQLite test DB.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete

import app.core.atlas.source.persistence as persistence
from app.core.atlas.source.persistence import list_app_maps, save_app_map
from app.models.app_map import AppMap


async def _get_app_map_by_id(db, mid: str) -> AppMap | None:
    return await db.get(AppMap, mid)


def _entity_payload(**overrides):
    payload = {
        "project_id": 1,
        "entity": "goods",
        "platform": "web",
        "aliases": ["商品"],
        "routes": [{"name": "list", "url": "/goods/list", "method": "GET"}],
        "actions": [
            {
                "name": "search",
                "kind": "read",
                "risk_tier": "ui",
                "controller": "C",
                "line": 1,
            }
        ],
        "elements": [{"name": "search_input", "page": "/goods/list", "line": 2}],
        "db_tables": [{"table": "goods", "pk": "id", "cols": ["id", "name"]}],
        "extra": {"base_url": "https://mall.local"},
    }
    payload.update(overrides)
    return payload


@pytest.fixture(autouse=True)
def _clean_appmaps(test_session_scope):
    import asyncio

    yield

    async def _clean():
        async with test_session_scope() as db:
            await db.execute(delete(AppMap))

    asyncio.run(_clean())


@pytest.fixture(autouse=True)
def _patch_scope(test_session_scope, monkeypatch):
    monkeypatch.setattr(persistence, "session_scope", test_session_scope)


@pytest.mark.asyncio
class TestSaveAppMap:
    async def test_creates_first_version(self, test_session_scope):
        mid, version, created = await save_app_map(**_entity_payload())
        assert created is True
        assert version == 1
        async with test_session_scope() as db:
            app_map = await _get_app_map_by_id(db, mid)
        assert app_map is not None
        assert app_map.entity == "goods"
        assert app_map.status == "active"

    async def test_unchanged_content_short_circuits(self):
        mid1, v1, created1 = await save_app_map(**_entity_payload())
        mid2, v2, created2 = await save_app_map(**_entity_payload())
        assert created1 is True
        assert created2 is False  # same content -> no new version
        assert mid1 == mid2
        assert v1 == v2

    async def test_changed_content_bumps_version_and_supersedes(
        self, test_session_scope
    ):
        mid1, v1, created1 = await save_app_map(**_entity_payload())
        changed = _entity_payload(
            elements=[{"name": "new_input", "page": "/goods/list", "line": 3}]
        )
        mid2, v2, created2 = await save_app_map(**changed)
        assert created2 is True
        assert v2 == v1 + 1
        assert mid2 != mid1
        # old map superseded, new active
        async with test_session_scope() as db:
            old = await db.get(AppMap, mid1)
            new = await db.get(AppMap, mid2)
            assert old.status == "superseded"
            assert new.status == "active"


@pytest.mark.asyncio
async def test_list_app_maps_filters_active():
    await save_app_map(**_entity_payload())
    maps = await list_app_maps(1, status="active")
    assert len(maps) == 1
    assert maps[0].entity == "goods"
