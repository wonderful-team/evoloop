"""Unit tests for atlas/source validate (schema + source spot-check)."""

from __future__ import annotations

from app.core.atlas.source.schemas import (
    AppMapAction,
    AppMapDbTable,
    AppMapElement,
    AppMapPayload,
    AppMapRoute,
)
from app.core.atlas.source.validate import validate_app_map


def _payload(**overrides) -> AppMapPayload:
    base = {
        "entity": "goods",
        "platform": "web",
        "aliases": ["商品"],
        "routes": [
            AppMapRoute(
                name="goods_list", url="/shop/goods/lists", source_action="lists"
            )
        ],
        "actions": [
            AppMapAction(
                name="lists",
                kind="read",
                risk_tier="ui",
                touches_tables=["goods"],
                controller="Goods.php",
                line=3,
            )
        ],
        "elements": [
            AppMapElement(
                name="js-save", page="edit_goods.html", line=2, binds="保存按钮"
            )
        ],
        "db_tables": [
            AppMapDbTable(table="goods", pk="goods_id", cols=["goods_id", "goods_name"])
        ],
    }
    base.update(overrides)
    return AppMapPayload(**base)


class TestSchemaValidation:
    async def test_clean_payload_passes(self):
        assert await validate_app_map(_payload()) == []

    async def test_illegal_kind(self):
        p = _payload(
            actions=[
                AppMapAction(
                    name="x",
                    kind="delete",
                    risk_tier="ui",
                    controller="Goods.php",
                    line=3,
                )
            ]
        )
        problems = await validate_app_map(p)
        assert any("kind" in m for m in problems)

    async def test_illegal_risk_tier(self):
        p = _payload(
            actions=[
                AppMapAction(
                    name="x",
                    kind="read",
                    risk_tier="admin",
                    controller="Goods.php",
                    line=3,
                )
            ]
        )
        problems = await validate_app_map(p)
        assert any("risk_tier" in m for m in problems)

    async def test_unknown_table_reference(self):
        p = _payload(
            actions=[
                AppMapAction(
                    name="x",
                    kind="read",
                    risk_tier="ui",
                    touches_tables=["orders"],
                    controller="Goods.php",
                    line=3,
                )
            ]
        )
        problems = await validate_app_map(p)
        assert any("orders" in m for m in problems)

    async def test_empty_route_url(self):
        p = _payload(routes=[AppMapRoute(name="r", url="")])
        problems = await validate_app_map(p)
        assert any("url" in m for m in problems)

    async def test_missing_provenance_flagged(self):
        p = _payload(actions=[AppMapAction(name="x", kind="read", risk_tier="ui")])
        problems = await validate_app_map(p, project_path="/nonexistent")
        assert any("controller/line" in m for m in problems)


class TestSourceSpotCheck:
    async def test_symbol_found_passes(self, tmp_path):
        (tmp_path / "Goods.php").write_text(
            "<?php\n// line2\nfunction lists() {}\nfunction editGoods() {}\n"
        )
        (tmp_path / "edit_goods.html").write_text("<div>js-save</div>\n")
        problems = await validate_app_map(_payload(), project_path=str(tmp_path))
        assert problems == []

    async def test_hallucinated_action_rejected(self, tmp_path):
        (tmp_path / "Goods.php").write_text("<?php\n// nothing here\n// line3\n")
        problems = await validate_app_map(_payload(), project_path=str(tmp_path))
        assert any("幻觉" in m for m in problems)

    async def test_missing_file_rejected(self, tmp_path):
        problems = await validate_app_map(_payload(), project_path=str(tmp_path))
        assert any("幻觉" in m for m in problems)

    async def test_nested_file_resolution(self, tmp_path):
        sub = tmp_path / "app" / "shop" / "controller"
        sub.mkdir(parents=True)
        (sub / "Goods.php").write_text("<?php\n// x\nfunction lists() {}\n")
        (tmp_path / "edit_goods.html").write_text("js-save\n")
        p = _payload(
            actions=[
                AppMapAction(
                    name="lists",
                    kind="read",
                    risk_tier="ui",
                    touches_tables=["goods"],
                    controller="app/shop/controller/Goods.php",
                    line=3,
                )
            ],
        )
        problems = await validate_app_map(p, project_path=str(tmp_path))
        assert problems == []


class TestBindsCoercion:
    async def test_binds_list_coerced_to_string(self):
        from app.core.atlas.source.schemas import AppMapElement

        el = AppMapElement(
            name="search_text", page="lists.html", line=42, binds=["input", "搜索框"]
        )
        assert el.binds == "input 搜索框"

    async def test_binds_string_passthrough(self):
        from app.core.atlas.source.schemas import AppMapElement

        el = AppMapElement(name="save", binds="保存按钮")
        assert el.binds == "保存按钮"
