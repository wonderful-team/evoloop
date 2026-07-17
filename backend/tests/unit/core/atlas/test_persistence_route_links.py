"""Unit tests for AppMapRouteLink population in save_app_map."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.atlas.source.persistence import save_app_map
from app.infrastructure.database import session_scope
from app.models.app_map import AppMap
from app.models.codebase import AppMapRouteLink, CodeChunk, Repository, SourceFile


async def _seed_codebase(db, project_id: int):
    repo = Repository(
        project_id=project_id,
        name="mall",
        url="https://example.com/mall",
        local_path="/tmp/mall",
    )
    db.add(repo)
    await db.flush()

    files = [
        SourceFile(
            repository_id=repo.id,
            path="app/shop/controller/Goods.php",
            checksum="a" * 64,
        ),
        SourceFile(
            repository_id=repo.id,
            path="app/shop/model/Goods.php",
            checksum="b" * 64,
        ),
    ]
    db.add_all(files)
    await db.flush()

    chunks = [
        CodeChunk(
            source_file_id=files[0].id,
            chunk_type="function",
            identifier="Goods.lists",
            start_line=1,
            end_line=10,
            content="function lists() {}",
            is_api_route=True,
            api_method="GET",
            api_path="/shop/goods/lists",
        ),
        CodeChunk(
            source_file_id=files[0].id,
            chunk_type="function",
            identifier="Goods.edit",
            start_line=20,
            end_line=30,
            content="function edit() {}",
            is_api_route=False,
        ),
        CodeChunk(
            source_file_id=files[1].id,
            chunk_type="class",
            identifier="Goods",
            start_line=1,
            end_line=50,
            content="class Goods {}",
            is_db_model=True,
            db_table_name="goods",
        ),
    ]
    db.add_all(chunks)
    await db.flush()
    return chunks, files


async def _fetch_links(db, app_map_id: int):
    stmt = select(AppMapRouteLink).where(AppMapRouteLink.app_map_id == app_map_id)
    result = await db.execute(stmt)
    return result.scalars().all()


class TestAppMapRouteLinkPopulation:
    async def test_verified_route_and_db_links(self, _real_db):
        async with session_scope() as db:
            await _seed_codebase(db, project_id=121)

        app_map_id, _, _ = await save_app_map(
            project_id=121,
            entity="goods",
            platform="web",
            aliases=["商品"],
            routes=[
                {
                    "name": "goods_list",
                    "url": "/shop/goods/lists",
                    "method": "GET",
                }
            ],
            actions=[
                {
                    "name": "lists",
                    "kind": "read",
                    "risk_tier": "ui",
                    "controller": "Goods.php",
                    "line": 3,
                }
            ],
            elements=[],
            db_tables=[{"table": "goods", "pk": "goods_id", "cols": ["goods_id"]}],
        )

        async with session_scope() as db:
            links = await _fetch_links(db, app_map_id)
            by_kind = {link.relation_kind: link for link in links}
            assert len(links) == 3
            route = by_kind["route"]
            assert route.is_verified
            assert route.logical_path == "/shop/goods/lists"
            assert route.logical_method == "GET"
            assert route.code_chunk_id is not None

            table = by_kind["db_table"]
            assert table.is_verified
            assert table.logical_path == "goods"
            assert table.code_chunk_id is not None

            action = by_kind["action"]
            assert action.is_verified
            assert action.code_chunk_id is not None

    async def test_unverified_route_when_no_matching_chunk(self, _real_db):
        async with session_scope() as db:
            await _seed_codebase(db, project_id=121)

        app_map_id, _, _ = await save_app_map(
            project_id=121,
            entity="orders",
            platform="web",
            aliases=["订单"],
            routes=[{"name": "orders_list", "url": "/shop/orders/lists", "method": "GET"}],
            actions=[],
            elements=[],
            db_tables=[{"table": "orders", "pk": "order_id", "cols": ["order_id"]}],
        )

        async with session_scope() as db:
            links = await _fetch_links(db, app_map_id)
            by_kind = {link.relation_kind: link for link in links}
            assert by_kind["route"].is_verified is False
            assert by_kind["route"].code_chunk_id is None
            assert by_kind["db_table"].is_verified is False
            assert by_kind["db_table"].code_chunk_id is None

    async def test_content_hash_short_circuit_keeps_existing_links(self, _real_db):
        async with session_scope() as db:
            await _seed_codebase(db, project_id=121)

        payload = {
            "project_id": 121,
            "entity": "goods",
            "platform": "web",
            "aliases": ["商品"],
            "routes": [
                {
                    "name": "goods_list",
                    "url": "/shop/goods/lists",
                    "method": "GET",
                }
            ],
            "actions": [],
            "elements": [],
            "db_tables": [{"table": "goods", "pk": "goods_id", "cols": ["goods_id"]}],
        }

        first_id, _, _ = await save_app_map(**payload)
        second_id, version, created = await save_app_map(**payload)

        assert second_id == first_id
        assert created is False

        async with session_scope() as db:
            stmt = (
                select(AppMap)
                .where(AppMap.id == first_id)
                .options(selectinload(AppMap.route_links))
            )
            result = await db.execute(stmt)
            app_map = result.scalar_one()
            assert len(app_map.route_links) == 2
            assert app_map.map_version == version
