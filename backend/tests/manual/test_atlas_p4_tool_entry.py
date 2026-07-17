"""P4 tool-entry validation: invoke write_app_map / generate_macros_from_app_map
THROUGH THE TOOL REGISTRY (the Agent's real call path), with EvoContext set,
then run the Huey task body and verify pending_review macros land in DB.
"""

import asyncio
import inspect
import logging
import os
from unittest.mock import patch

logging.disable(logging.CRITICAL)

DB = "/var/folders/h7/llqy_6yj04g6t9ls9gk8kgzw0000gn/T/opencode/atlas_p4_tool_test.db"
os.environ["SQLITE_PATH"] = DB
if os.path.exists(DB):
    os.remove(DB)

PROJECT_PATH = "/Users/huangjinhuan/Projects/develop-assistant.cn/member-center/backend"
PROJECT_ID = 77

STEP = 0


def step(msg):
    global STEP
    STEP += 1
    print(f"[{STEP}] {msg}")


async def main():
    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=True, seed_data=False)

    # EvoContext: project + working directory (as the engine would set)
    from app.core.context.manager import ContextManager, EvoContext

    ctx = EvoContext(
        thread_id="thread-p4",
        project_id=PROJECT_ID,
        member_id=0,
        working_directory=PROJECT_PATH,
    )
    token = ContextManager.set(ctx)

    try:
        # ---------- 1. tools visible in registry ----------
        from app.core.tools.registry import get_tool_map

        tool_map = get_tool_map()
        for name in (
            "write_app_map",
            "read_app_map",
            "list_app_maps",
            "generate_macros_from_app_map",
        ):
            assert name in tool_map, f"{name} not in registry"
        step(
            "注册表可见: write_app_map / read_app_map / list_app_maps / generate_macros_from_app_map"
        )

        write_tool = tool_map["write_app_map"]

        # ---------- 2. write_app_map rejects hallucination ----------
        bad_args = {
            "entity": "goods",
            "platform": "admin",
            "aliases": ["商品"],
            "routes": [
                {
                    "name": "r",
                    "url": "/shop/goods/lists",
                    "method": "GET",
                    "source_action": "lists",
                }
            ],
            "actions": [
                {
                    "name": "fakeAction",
                    "kind": "read",
                    "risk_tier": "ui",
                    "controller": "app/shop/controller/Goods.php",
                    "line": 10,
                }
            ],
            "elements": [],
            "db_tables": [],
        }
        res = await write_tool.ainvoke(bad_args)
        assert "validation failed" in str(res).lower() or "疑似幻觉" in str(res), res
        step("write_app_map 拒绝幻觉 payload（未落库）")

        # ---------- 3. write_app_map accepts real payload ----------
        good_args = {
            "entity": "goods",
            "platform": "admin",
            "aliases": ["商品"],
            "routes": [
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
            ],
            "actions": [
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
            ],
            "elements": [
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
            "db_tables": [
                {"table": "goods", "pk": "goods_id", "cols": ["goods_name", "price"]}
            ],
        }
        res = await write_tool.ainvoke(good_args)
        assert "saved as v1" in str(res), res
        step(f"write_app_map 落库: {str(res)[:80]}")

        # ---------- 4. read/list via registry ----------
        from app.core.atlas.source import persistence

        active = await persistence.get_active_app_map(PROJECT_ID, "goods")
        assert active is not None and active.generation_thread_id == "thread-p4"
        res = await tool_map["list_app_maps"].ainvoke({})
        assert "goods" in str(res)
        res = await tool_map["read_app_map"].ainvoke({"entity": "goods"})
        assert "editGoods" in str(res)
        step(
            f"read_app_map / list_app_maps 正常（map id={active.id}, thread 溯源正确）"
        )

        # ---------- 5. generate tool dispatches Huey task ----------
        gen_tool = tool_map["generate_macros_from_app_map"]
        dispatched = {}

        class FakeTask:
            @staticmethod
            def delay(**kwargs):
                dispatched.update(kwargs)

        with patch("app.core.execution.macro.tasks.synthesize_macros_task", FakeTask):
            res = await gen_tool.ainvoke({"app_map_id": active.id})
        assert (
            "synthesis started" in str(res).lower() or "started" in str(res).lower()
        ), res
        assert dispatched == {
            "app_map_id": active.id,
            "project_id": PROJECT_ID,
            "member_id": 0,
        }, dispatched
        step(f"generate_macros_from_app_map → Huey 派发参数正确: {dispatched}")

        # ---------- 6. task body produces pending_review macros ----------
        from app.core.execution.macro import tasks as macro_tasks

        wrapped = macro_tasks.synthesize_macros_task
        raw = None
        # Huey TaskWrapper -> _huey_wrapper closure captures the original coroutine
        fn = getattr(wrapped, "func", wrapped)
        if inspect.iscoroutinefunction(fn):
            raw = fn
        else:
            for cell in getattr(fn, "__closure__", None) or []:
                cand = cell.cell_contents
                if inspect.iscoroutinefunction(cand):
                    raw = cand
                    break
        assert raw is not None, f"cannot unwrap task body: {wrapped}"

        out = await raw(app_map_id=active.id, project_id=PROJECT_ID, member_id=0)
        assert out["candidates"] == 2, out
        step(f"任务体执行: {out['candidates']} 候选, gaps={out['gaps']}")

        from app.core.execution.macro import lifecycle

        pending = await lifecycle.list_macros(
            project_id=PROJECT_ID, status="pending_review"
        )
        assert len(pending) == 2
        assert all(not m.is_active for m in pending)
        names = sorted(m.name for m in pending)
        step(f"宏库出现 pending_review 候选（未确认不可路由）: {names}")

        # ---------- 7. non-active map rejected ----------
        await persistence.save_app_map(
            project_id=PROJECT_ID,
            entity="goods",
            platform="admin",
            aliases=["商品"],
            routes=good_args["routes"],
            actions=good_args["actions"]
            + [
                {
                    "name": "addGoods",
                    "kind": "write",
                    "risk_tier": "data",
                    "controller": "app/shop/controller/Goods.php",
                    "line": 286,
                }
            ],
            elements=good_args["elements"],
            db_tables=good_args["db_tables"],
        )
        old = await persistence.get_app_map(active.id)
        assert old.status == "superseded"
        with patch("app.core.execution.macro.tasks.synthesize_macros_task", FakeTask):
            res = await gen_tool.ainvoke({"app_map_id": active.id})
        assert "superseded" in str(res), res
        step("superseded 地图被拒生成（只有 active 可生成）")

    finally:
        ContextManager.reset(token)
        await db_resource_manager.shutdown()

    print("\n✅ P4 工具入口验证全部通过 (7 步)")


asyncio.run(main())
