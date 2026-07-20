"""Unit tests for atlas/source template factory (grounding rule)."""

from __future__ import annotations

from app.core.atlas.source.macro_factory import pick_template, synthesize
from app.core.execution.macro.schemas import MacroScript

GOODS_MAP = {
    "entity": "goods",
    "aliases": ["商品", "铰链"],
    "routes": [
        {
            "name": "goods_list",
            "url": "/shop/goods/lists",
            "method": "GET",
            "source_action": "lists",
        },
        {
            "name": "goods_edit",
            "url": "/shop/goods/editgoods",
            "method": "GET/POST",
            "source_action": "editGoods",
        },
    ],
    "actions": [
        {
            "name": "lists",
            "kind": "read",
            "risk_tier": "ui",
            "touches_tables": ["goods"],
            "business_rule": "商品列表",
            "controller": "Goods.php",
            "line": 50,
        },
        {
            "name": "getGoodsSkuList",
            "kind": "read",
            "risk_tier": "data",
            "touches_tables": ["sku"],
            "business_rule": "取 SKU 列表",
            "controller": "Goods.php",
            "line": 760,
        },
        {
            "name": "editGoods",
            "kind": "write",
            "risk_tier": "money",
            "touches_tables": ["sku"],
            "set_fields": ["price"],
            "pk": "sku_id",
            "business_rule": "改价",
            "controller": "Goods.php",
            "line": 430,
        },
    ],
    "elements": [
        {
            "name": "edit_price",
            "page": "edit_goods.html",
            "line": 433,
            "binds": "SKU 价格输入框",
            "selector_type": "id",
        },
        {
            "name": "edit_sku_id",
            "page": "edit_goods.html",
            "line": 429,
            "binds": "SKU id",
        },
        {
            "name": "js-save",
            "page": "edit_goods.html",
            "line": 693,
            "binds": "保存按钮",
            "selector_type": "class",
        },
        {
            "name": "search_text",
            "page": "lists.html",
            "line": 42,
            "binds": "搜索框 商品名称",
            "selector_type": "name",
        },
        {
            "name": "search",
            "page": "lists.html",
            "line": 152,
            "binds": "搜索提交按钮",
            "selector_type": "lay-filter",
        },
        {
            "name": "goods_list",
            "page": "lists.html",
            "line": 169,
            "binds": "商品列表结果表格",
            "selector_type": "id",
        },
        {
            "name": "data-goods-id",
            "page": "lists.html",
            "line": 222,
            "binds": "行内数据ID",
            "selector_type": "data-attr",
        },
    ],
    "db_tables": [
        {"table": "sku", "pk": "sku_id", "cols": ["sku_id", "goods_id", "price"]},
        {"table": "goods", "pk": "goods_id", "cols": ["goods_id", "goods_name"]},
    ],
    "map_version": 1,
}


class TestPickTemplate:
    def test_read_ui(self):
        assert pick_template({"kind": "read", "risk_tier": "ui"}) is not None

    def test_read_data(self):
        assert pick_template({"kind": "read", "risk_tier": "data"}) is not None

    def test_write_money(self):
        assert pick_template({"kind": "write", "risk_tier": "money"}) is not None

    def test_unmatched_returns_none(self):
        from app.core.atlas.source.macro_factory.templates import basic_navigate
        # write/ui now maps to basic_navigate (v3.5 change)
        assert pick_template({"kind": "write", "risk_tier": "ui"}) is basic_navigate
        assert pick_template({"kind": "read", "risk_tier": "money"}) is None


class TestSynthesizeGrounding:
    def test_crud_write_produced_with_confirmation(self):
        result = synthesize(GOODS_MAP)
        write = [
            c
            for c in result.candidates
            if c.source_action == "editGoods" and c.requires_confirmation
        ]
        assert len(write) == 1
        assert write[0].requires_confirmation is True
        assert write[0].risk_tier == "money"

    def test_money_write_also_produces_field_read(self):
        # The sibling field-read macro ('查{query}商品价格') shares the write's
        # grounding but never writes: risk ui, no confirmation, `value` key.
        result = synthesize(GOODS_MAP)
        read = [
            c
            for c in result.candidates
            if c.source_action == "editGoods" and not c.requires_confirmation
        ]
        assert len(read) == 1
        assert read[0].risk_tier == "ui"
        assert any(s.get("key") == "value" for s in read[0].macro_script)

    def test_ungroundable_actions_become_gaps(self):
        result = synthesize(GOODS_MAP)
        gap_text = "\n".join(result.gaps)
        assert "goods.getGoodsSkuList" in gap_text

    def test_no_validation_errors_on_clean_map(self):
        result = synthesize(GOODS_MAP)
        assert result.validation_errors == []

    def test_candidates_parse_as_macro_script(self):
        result = synthesize(GOODS_MAP)
        for c in result.candidates:
            script = MacroScript(steps=c.macro_script)
            assert len(script.steps) >= 1

    def test_yaml_round_trip(self):
        result = synthesize(GOODS_MAP)
        for c in result.candidates:
            yaml_str = MacroScript(steps=c.macro_script).to_yaml()
            reparsed = MacroScript.from_yaml(yaml_str)
            assert len(reparsed.steps) == len(c.macro_script)

    def test_grounding_rejects_foreign_url(self):
        result = synthesize(GOODS_MAP)
        candidate = next(c for c in result.candidates if c.source_action == "editGoods")
        candidate.macro_script[0]["payload"]["url"] = "/evil/unknown"
        from app.core.atlas.source.macro_factory.synthesizer import _check_candidate

        problems = _check_candidate(candidate, GOODS_MAP)
        assert any("不在 AppMap routes" in p for p in problems)

    def test_grounding_rejects_foreign_selector(self):
        result = synthesize(GOODS_MAP)
        candidate = result.candidates[0]
        candidate.macro_script[2]["target_selector"] = "不存在的元素"
        from app.core.atlas.source.macro_factory.synthesizer import _check_candidate

        problems = _check_candidate(candidate, GOODS_MAP)
        assert any("不在 AppMap elements" in p for p in problems)

    def test_duplicate_names_suffixed_with_source_action(self):
        dup_map = dict(GOODS_MAP)
        dup_map["actions"] = GOODS_MAP["actions"] + [
            {
                "name": "addGoods",
                "kind": "write",
                "risk_tier": "money",
                "touches_tables": ["sku"],
                "set_fields": ["price"],
                "business_rule": "新增商品",
                "controller": "Goods.php",
                "line": 286,
            },
        ]
        dup_map["routes"] = GOODS_MAP["routes"] + [
            {
                "name": "goods_add",
                "url": "/shop/goods/addgoods",
                "method": "GET/POST",
                "source_action": "addGoods",
            }
        ]
        result = synthesize(dup_map)
        names = [
            c.name
            for c in result.candidates
            if c.source_action in {"addGoods", "editGoods"}
        ]
        # Each money write yields two candidates (write + sibling field-read).
        assert len(names) == 4
        assert len(set(names)) == 4
        assert any("（addGoods）" in n for n in names)

    def test_list_view_grounds_on_english_list_symbol(self):
        lv_map = dict(GOODS_MAP)
        lv_map["elements"] = GOODS_MAP["elements"] + [
            {
                "name": "search_text",
                "page": "lists.html",
                "line": 42,
                "binds": "搜索框",
            },
            {
                "name": "goods_list",
                "page": "lists.html",
                "line": 169,
                "binds": "结果表格",
            },
        ]
        result = synthesize(lv_map)
        names = [c.name for c in result.candidates]
        assert any("查看" in n for n in names), names


class TestExecutableFormat:
    """Macro scripts must be self-contained: navigable URL + typed selector."""

    def _write_candidate(self, entity_map=None):
        result = synthesize(entity_map or GOODS_MAP)
        return next(c for c in result.candidates if c.source_action == "editGoods")

    def test_url_has_base_placeholder_when_origin_unknown(self):
        candidate = self._write_candidate()
        url = candidate.macro_script[0]["payload"]["url"]
        assert url == "{{base_url}}/shop/goods/lists"
        assert any(p["name"] == "base_url" for p in candidate.parameters)

    def test_url_full_when_base_url_known(self):
        m = dict(GOODS_MAP)
        m["extra"] = {"base_url": "http://mall.local:8080/"}
        candidate = self._write_candidate(m)
        url = candidate.macro_script[0]["payload"]["url"]
        assert url == "http://mall.local:8080/shop/goods/lists"
        assert all(p["name"] != "base_url" for p in candidate.parameters)

    def test_route_without_leading_slash_normalized(self):
        m = dict(GOODS_MAP)
        m["routes"] = [
            dict(r, url="shop/goods/lists") if r["source_action"] == "lists" else r
            for r in GOODS_MAP["routes"]
        ]
        candidate = self._write_candidate(m)
        assert "/shop/goods/lists" in candidate.macro_script[0]["payload"]["url"]

    def test_typed_selector_prefixed(self):
        candidate = self._write_candidate()
        selectors = [s.get("target_selector") for s in candidate.macro_script]
        assert "#edit_price" in selectors
        assert ".js-save" in selectors

    def test_untyped_selector_falls_back_to_union(self):
        m = dict(GOODS_MAP)
        m["elements"] = [
            {**e, "selector_type": None} if e["name"] == "edit_price" else e
            for e in GOODS_MAP["elements"]
        ]
        candidate = self._write_candidate(m)
        selectors = [s.get("target_selector") for s in candidate.macro_script]
        assert "#edit_price, [name='edit_price']" in selectors

    def test_write_input_does_not_enter_before_save_click(self):
        candidate = self._write_candidate()
        value_input = next(
            s
            for s in candidate.macro_script
            if s["event_type"] == "input" and "{{new_value}}" in s["payload"]["text"]
        )
        assert value_input["payload"]["enter"] is False
        assert candidate.macro_script[-1]["event_type"] == "click"

    def test_two_stage_search_then_edit_by_extracted_id(self):
        candidate = self._write_candidate()
        events = [s["event_type"] for s in candidate.macro_script]
        assert events[0] == "navigate"  # list page
        extract = next(s for s in candidate.macro_script if s["type"] == "extract")
        assert extract["extract_type"] == "get_attribute"
        assert extract["key"] == "entity_id"
        assert extract["payload"]["attribute"] == "data-goods-id"
        assert "[lay-id='goods_list']" in extract["target_selector"]
        assert "[data-goods-id]" in extract["target_selector"]
        edit_nav = candidate.macro_script[-4]
        assert edit_nav["event_type"] == "navigate"
        assert edit_nav["payload"]["url"].endswith(
            "/shop/goods/editgoods?id={{entity_id}}"
        )

    def test_write_gap_when_row_id_element_missing(self):
        m = dict(GOODS_MAP)
        m["elements"] = [
            e for e in GOODS_MAP["elements"] if e["name"] != "data-goods-id"
        ]
        result = synthesize(m)
        assert not [c for c in result.candidates if c.source_action == "editGoods"]
        assert any("editGoods" in g for g in result.gaps)

    def test_post_only_route_becomes_gap(self):
        m = dict(GOODS_MAP)
        m["routes"] = [
            dict(r, method="POST") if r["source_action"] == "editGoods" else r
            for r in GOODS_MAP["routes"]
        ]
        result = synthesize(m)
        assert not [c for c in result.candidates if c.source_action == "editGoods"]
        assert any("editGoods" in g for g in result.gaps)

    def test_list_view_clicks_button_instead_of_double_enter(self):
        result = synthesize(GOODS_MAP)
        lv = next(c for c in result.candidates if c.name.startswith("查看"))
        events = [s["event_type"] for s in lv.macro_script]
        assert "key_press" not in events
        input_step = next(s for s in lv.macro_script if s["event_type"] == "input")
        assert input_step["payload"]["enter"] is False
        click = next(s for s in lv.macro_script if s["event_type"] == "click")
        assert "search" in click["target_selector"]

    def test_list_view_enters_when_no_button(self):
        lv_map = dict(GOODS_MAP)
        lv_map["elements"] = [e for e in GOODS_MAP["elements"] if e["name"] != "search"]
        result = synthesize(lv_map)
        lv = next(c for c in result.candidates if c.name.startswith("查看"))
        input_step = next(s for s in lv.macro_script if s["event_type"] == "input")
        assert input_step["payload"]["enter"] is True
