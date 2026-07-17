"""Clarify loop + frame probe E2E against the live mall admin.

    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=xxx \
        .venv/bin/python tests/manual/test_multiturn_clarify_e2e.py

Turns (one thread):
  A. "把它的库存改成142" with EMPTY frame -> clarify decision (请问是哪个商品？),
     pending stored, nothing executes.
  B. "夜光亚克力钥匙扣" -> answer spliced into pending text -> write macro #54
     routed with query/new_value=142 -> money HITL delegate (captured).
  C. "查一下夜光亚克力钥匙扣的价格" -> real #107 run, frame learns entity.
  D. user MANUALLY navigates away (probe scenario), then "把它的库存改成142"
     -> route-time probe mismatch clears the frame -> clarify again.
  E. "夜光亚克力钥匙扣" -> resume -> #54 money HITL again.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

BASE = "http://127.0.0.1:9002"
THREAD = "mt-clarify"


async def login(page) -> None:
    await page.goto(f"{BASE}/shop.html", wait_until="load", timeout=30000)
    await page.wait_for_timeout(1500)
    if "login" in page.url:
        await page.fill("[name='username']", os.environ["MALL_ADMIN_USER"])
        await page.fill("[name='password']", os.environ["MALL_ADMIN_PASS"])
        await page.click("[lay-filter='login']")
        await page.wait_for_timeout(3000)
    assert "login" not in page.url, "登录失败"
    print("[e2e] 登录态 OK")


async def main() -> None:
    from app.core.routing import executor, retriever, session_frame
    from app.core.routing import router as route_router
    from app.core.routing.schemas import RouteRequest
    from app.core.routing.sync import rebuild_route_index
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.infrastructure.drivers.browser import browser_manager

    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    await rebuild_route_index()

    page = await browser_manager.get_page(thread_id=THREAD)
    await login(page)

    session_frame.clear_frame(THREAD)
    failures = []

    delegated = []
    orig_run_agent = executor._run_agent

    async def capture_agent(*_, **kw):
        delegated.append(kw)

    executor._run_agent = capture_agent

    async def turn(text: str, execute: bool = True):
        print(f"\n===== TURN: {text} =====")
        req = RouteRequest(text=text, thread_id=THREAD)
        candidates = await retriever.retrieve(text, top_k=20)
        decisions = await route_router.route_many(req, candidates)
        d0 = decisions[0]
        pub = {k: v for k, v in (d0.params or {}).items() if not k.startswith("_")}
        print(f"  -> status={d0.status} type={d0.target_type} target={d0.target} params={pub}")
        if execute and d0.target_type in ("skill", "macro", "agent"):
            await executor.execute_many(THREAD, decisions)
        frame = session_frame.get_frame(THREAD)
        print(f"  frame: page={frame and frame.current_page} entity={frame and frame.current_entity} pending={frame and frame.pending}")
        return d0

    try:
        # ── A: 冷启动指代 → clarify ───────────────────────────────
        d = await turn("把它的库存改成142")
        if d.status != "clarify" or "哪个商品" not in (d.params or {}).get("question", ""):
            failures.append(f"A 应 clarify(商品): status={d.status} params={d.params}")
        frame = session_frame.get_frame(THREAD)
        if not frame or not frame.pending:
            failures.append(f"A pending 未存: {frame and frame.pending}")

        # ── B: 作答 → 合成 → 宏54 money HITL ─────────────────────
        delegated.clear()
        d = await turn("夜光亚克力钥匙扣")
        if d.target_type != "macro" or d.target.get("id") != 54:
            failures.append(f"B 合成后未命中宏54: {d.target}")
        elif (d.params or {}).get("query") != "夜光亚克力钥匙扣" or (d.params or {}).get("new_value") != 142:
            failures.append(f"B 参数异常: {d.params}")
        if not delegated or delegated[0]["metadata"].get("macro_id") != 54:
            failures.append(f"B money 门未委派宏54: {delegated}")
        frame = session_frame.get_frame(THREAD)
        if frame and frame.pending:
            failures.append(f"B 后 pending 未消费: {frame.pending}")

        # ── C: 真实查价建帧 ───────────────────────────────────────
        d = await turn("查一下夜光亚克力钥匙扣的价格")
        frame = session_frame.get_frame(THREAD)
        if not frame or not frame.current_entity:
            failures.append(f"C 帧未建实体: {frame and frame.current_entity}")

        # ── D: 用户手动切页 → 探针清帧 → 指代再问 clarify ──────────
        await page.goto(f"{BASE}/shop/order/lists", wait_until="load", timeout=30000)
        await page.wait_for_timeout(1000)
        d = await turn("把它的库存改成142")
        if d.status != "clarify":
            failures.append(f"D 探针后应 clarify: status={d.status} target={d.target}")

        # ── E: 再作答 → 宏54 money HITL ──────────────────────────
        delegated.clear()
        d = await turn("夜光亚克力钥匙扣")
        if d.target_type != "macro" or d.target.get("id") != 54:
            failures.append(f"E 合成后未命中宏54: {d.target}")
        if not delegated or delegated[0]["metadata"].get("macro_id") != 54:
            failures.append(f"E money 门未委派宏54: {delegated}")
    finally:
        executor._run_agent = orig_run_agent
        session_frame.clear_frame(THREAD)

    print("\n" + ("=" * 40))
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        sys.exit(1)
    print("CLARIFY+PROBE PASS")


asyncio.run(main())
