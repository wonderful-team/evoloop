"""Backend chain validation: AppMap -> validate -> save -> synthesize -> persist
-> confirm -> route entries -> _run_macro preflight+execution (MacroEngine mocked).

Runs against REAL member-center/backend source with REAL citations.
"""

import asyncio
import logging
import os
from unittest.mock import patch

logging.disable(logging.CRITICAL)

os.environ["SQLITE_PATH"] = (
    "/var/folders/h7/llqy_6yj04g6t9ls9gk8kgzw0000gn/T/opencode/atlas_chain_test.db"
)
if os.path.exists(os.environ["SQLITE_PATH"]):
    os.remove(os.environ["SQLITE_PATH"])

PROJECT_PATH = "/Users/huangjinhuan/Projects/develop-assistant.cn/member-center/backend"
PROJECT_ID = 42

STEP = 0


def step(msg):
    global STEP
    STEP += 1
    print(f"[{STEP}] {msg}")


async def main():
    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=True, seed_data=False)

    from app.core.atlas.source.macro_factory.synthesizer import synthesize
    from app.core.atlas.source.persistence import save_app_map
    from app.core.atlas.source.schemas import AppMapPayload
    from app.core.atlas.source.validate import validate_app_map
    from app.core.execution.macro import lifecycle

    # ---------- payload with REAL citations ----------
    payload = AppMapPayload(
        entity="goods",
        platform="admin",
        aliases=["商品"],
        routes=[
            {
                "name": "商品列表",
                "url": "/shop/goods/lists",
                "method": "GET",
                "source_action": "lists",
            },
            {
                "name": "编辑商品",
                "url": "/shop/goods/editGoods",
                "method": "GET",
                "source_action": "editGoods",
            },
            {
                "name": "SKU查询",
                "url": "/shop/goods/getGoodsSkuList",
                "method": "GET",
                "source_action": "getGoodsSkuList",
            },
        ],
        actions=[
            {
                "name": "lists",
                "kind": "read",
                "risk_tier": "ui",
                "business_rule": "商品列表搜索",
                "controller": "app/shop/controller/Goods.php",
                "line": 50,
            },
            {
                "name": "editGoods",
                "kind": "write",
                "risk_tier": "money",
                "business_rule": "编辑商品价格",
                "touches_tables": ["goods"],
                "set_fields": ["价格"],
                "controller": "app/shop/controller/Goods.php",
                "line": 430,
            },
            {
                "name": "getGoodsSkuList",
                "kind": "read",
                "risk_tier": "data",
                "business_rule": "查询商品SKU库存",
                "set_fields": ["价格"],
                "controller": "app/shop/controller/Goods.php",
                "line": 760,
            },
        ],
        elements=[
            {
                "name": "search_text",
                "page": "app/shop/view/goods/lists.html",
                "line": 42,
                "binds": "search 搜索框",
            },
            {
                "name": "goods_list",
                "page": "app/shop/view/goods/lists.html",
                "line": 169,
                "binds": "商品列表 table 表格",
            },
            {
                "name": "price",
                "page": "app/shop/view/goods/edit_goods.html",
                "line": 342,
                "binds": "价格 销售价 input",
            },
            {
                "name": "save",
                "page": "app/shop/view/goods/edit_goods.html",
                "line": 693,
                "binds": "保存 提交按钮",
            },
        ],
        db_tables=[
            {"table": "goods", "pk": "goods_id", "cols": ["goods_name", "price"]}
        ],
    )

    # ---------- 1. validate (schema + source spot-check) ----------
    problems = await validate_app_map(payload, project_path=PROJECT_PATH)
    assert problems == [], f"validation should pass: {problems}"
    step("validate_app_map: 真实引用全部通过（schema + 回源抽检）")

    # ---------- 2. hallucination rejection ----------
    bad = payload.model_copy(deep=True)
    from app.core.atlas.source.schemas import AppMapAction

    bad.actions.append(
        AppMapAction(
            name="flyToMoon",
            kind="read",
            risk_tier="ui",
            controller="app/shop/controller/Goods.php",
            line=10,
        )
    )
    bad_problems = await validate_app_map(bad, project_path=PROJECT_PATH)
    assert any("flyToMoon" in p for p in bad_problems), bad_problems
    step(f"幻觉条目被拒: {bad_problems[0]}")

    # ---------- 3. save ----------
    app_map_id, version, created = await save_app_map(
        project_id=PROJECT_ID,
        entity=payload.entity,
        platform=payload.platform,
        aliases=payload.aliases,
        routes=[r.model_dump() for r in payload.routes],
        actions=[a.model_dump() for a in payload.actions],
        elements=[e.model_dump() for e in payload.elements],
        db_tables=[t.model_dump() for t in payload.db_tables],
    )
    assert created and version == 1
    step(f"save_app_map: id={app_map_id} v{version}")

    # ---------- 4. synthesize ----------
    entity_map = {
        "entity": "goods",
        "map_version": version,
        "routes": [r.model_dump() for r in payload.routes],
        "actions": [a.model_dump() for a in payload.actions],
        "elements": [e.model_dump() for e in payload.elements],
    }
    result = synthesize(entity_map)
    names = [c.name for c in result.candidates]
    assert "查看{query}goods" in names, names
    assert "改{query}goods价格" in names, names
    assert "查{query}goods价格" in names, names
    money = next(c for c in result.candidates if c.source_action == "editGoods")
    assert money.requires_confirmation and money.risk_tier == "money"
    step(f"synthesize: 3 个候选宏 {names}（money 宏带确认门）")

    # ---------- 5. persist + confirm ----------
    ids = await lifecycle.persist_candidates(
        app_map_id=app_map_id,
        entity="goods",
        project_id=PROJECT_ID,
        candidates=result.candidates,
    )
    assert len(ids) == 3
    confirmed = await lifecycle.confirm_bulk(ids)
    assert confirmed == 3
    step(f"persist_candidates + confirm_bulk: {ids}")

    # ---------- 6. active index (P5 context) ----------
    idx = await lifecycle.list_active_macro_index(project_id=PROJECT_ID)
    assert len(idx) == 3
    step(f"list_active_macro_index: {[m['name'] for m in idx]}")

    # ---------- 7. route entries ----------
    from app.core.routing import sync as route_sync

    entries = route_sync._macro_entries()
    our = [e for e in entries if e["id"] in {f"macro:{i}" for i in ids}]
    assert len(our) == 3, our
    assert all(e["type"] == "macro" for e in our)
    step("sync._macro_entries: 3 条 macro 进入路由索引")

    # ---------- 8. _run_macro end-to-end (MacroEngine mocked) ----------
    from app.core.routing import executor
    from app.core.routing.schemas import RouteDecision

    pushed = []

    async def fake_push(_thread_id, status, summary):
        pushed.append((status, summary))

    executed = {}

    class FakeEngine:
        @staticmethod
        async def execute(thread_id, script, params=None):
            executed["steps"] = len(script.steps)
            executed["params"] = params
            return True, "ok", {}

    decision = RouteDecision(
        target_type="macro",
        target={"id": ids[0]},  # list_view macro
        params={"query": "测试商品"},
        reason="chain-test",
    )

    with (
        patch.object(executor, "push_voice_result", fake_push),
        patch("app.core.execution.macro.engine.MacroEngine", FakeEngine),
    ):
        await executor._run_macro("thread-chain-1", decision)

    assert pushed and pushed[-1][0] == "done", pushed
    assert executed["steps"] == 6, executed
    assert executed["params"]["_macro_id"] == ids[0]
    assert executed["params"]["query"] == "测试商品"
    step("_run_macro(list_view): done, 6 步脚本, 参数注入正确")

    # ---------- 8b. money HITL gate ----------
    with (
        patch.object(executor, "push_voice_result", fake_push),
        patch("app.core.execution.macro.engine.MacroEngine", FakeEngine),
    ):
        money_decision = RouteDecision(
            target_type="macro",
            target={"id": ids[1]},
            params={"query": "测试商品", "new_value": 9.9},
            reason="t",
        )
        await executor._run_macro("thread-chain-1b", money_decision)
    assert pushed[-1][0] == "confirm_required", pushed[-1]
    step(f"money 确认门: {pushed[-1][0]} — {pushed[-1][1]}")

    # ---------- 9. gates: missing params / unroutable ----------
    with patch.object(executor, "push_voice_result", fake_push):
        bad_decision = RouteDecision(
            target_type="macro", target={"id": ids[0]}, params={}, reason="t"
        )
        await executor._run_macro("thread-chain-2", bad_decision)
    assert pushed[-1][0] == "failed" and "缺少参数" in pushed[-1][1], pushed[-1]
    step(f"缺参门拦截: {pushed[-1][1]}")

    await lifecycle.delete_macro(ids[1])
    with patch.object(executor, "push_voice_result", fake_push):
        gone = RouteDecision(
            target_type="macro",
            target={"id": ids[1]},
            params={"query": "x", "new_value": 9.9},
            reason="t",
        )
        await executor._run_macro("thread-chain-3", gone)
    assert pushed[-1][0] == "failed" and "not found" in pushed[-1][1]
    step(f"删除后拦截: {pushed[-1][1]}")

    # ---------- 10. supersede cascade ----------
    _, v2, created2 = await save_app_map(
        project_id=PROJECT_ID,
        entity="goods",
        platform="admin",
        aliases=["商品"],
        routes=[r.model_dump() for r in payload.routes],
        actions=[a.model_dump() for a in payload.actions]
        + [
            {
                "name": "addGoods",
                "kind": "write",
                "risk_tier": "data",
                "business_rule": "新增商品",
                "controller": "app/shop/controller/Goods.php",
                "line": 286,
            }
        ],
        elements=[e.model_dump() for e in payload.elements],
        db_tables=[t.model_dump() for t in payload.db_tables],
    )
    assert created2 and v2 == 2
    obsoleted = await lifecycle.mark_obsolete_by_app_map(app_map_id)
    remaining = await lifecycle.list_active_macro_index(project_id=PROJECT_ID)
    assert obsoleted == 2, obsoleted  # ids[0], ids[2] (ids[1] deleted)
    assert remaining == [], remaining
    step(f"重新调研 v{v2} → 旧图宏批量 obsolete ({obsoleted} 条)，活跃索引清空")

    await db_resource_manager.shutdown()
    print("\n✅ 后端链路验证全部通过 (10 步)")


asyncio.run(main())
