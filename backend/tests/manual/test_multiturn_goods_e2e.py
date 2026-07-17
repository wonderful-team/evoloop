"""Multi-turn conversation E2E: three turns sharing one thread_id against the
live mall admin (http://127.0.0.1:9002).

    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=xxx \
        .venv/bin/python tests/manual/test_multiturn_goods_e2e.py

Turns (goods scenario, all macros already verified):
  1. "打开商品列表"            — list_open navigation macro (#110), no query;
     frame learns current_page = goods lists url.
  2. "查一下夜光亚克力钥匙扣的价格" — field-read macro #107 extracts the real
     price; frame learns current_entity.query = 夜光亚克力钥匙扣.
  3. "把它的库存改成142"       — anaphora rewrite (它 -> 夜光亚克力钥匙扣)
     routes write macro #54 with new_value=142; money tier hits the §16.5
     HITL delegate (captured, everything before it is real).
"""

import asyncio
import os
import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

BASE = "http://127.0.0.1:9002"
THREAD = "mt-goods"


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
    indexed = await rebuild_route_index()
    print(f"[e2e] 路由索引重建: {indexed} 条")

    page = await browser_manager.get_page()
    await login(page)

    session_frame.clear_frame(THREAD)
    failures = []

    delegated = []
    orig_run_agent = executor._run_agent

    async def capture_agent(*a, **kw):
        delegated.append(kw)

    executor._run_agent = capture_agent

    async def turn(text: str):
        print(f"\n===== TURN: {text} =====")
        req = RouteRequest(text=text, thread_id=THREAD)
        candidates = await retriever.retrieve(text, top_k=20)
        decisions = await route_router.route_many(req, candidates)
        for d in decisions:
            pub = {k: v for k, v in (d.params or {}).items() if not k.startswith("_")}
            print(f"  -> type={d.target_type} target={d.target} params={pub}")
        await executor.execute_many(THREAD, decisions)
        frame = session_frame.get_frame(THREAD)
        print(f"  frame: page={frame and frame.current_page} entity={frame and frame.current_entity}")
        return decisions

    try:
        # ── Turn 1: 纯导航 ─────────────────────────────────────────
        decisions = await turn("打开商品列表")
        d0 = decisions[0]
        if d0.target_type != "macro" or d0.target.get("id") != 110:
            failures.append(f"Turn1 未命中打开商品列表宏110: {d0.target}")
        frame = session_frame.get_frame(THREAD)
        if frame is None or not frame.current_page or "goods" not in frame.current_page:
            failures.append(f"Turn1 帧未记录商品列表页: {frame and frame.current_page}")

        # ── Turn 2: 真实查价，帧学到当前实体 ───────────────────────
        decisions = await turn("查一下夜光亚克力钥匙扣的价格")
        d0 = decisions[0]
        if d0.target_type != "macro" or d0.target.get("id") != 107:
            failures.append(f"Turn2 未命中查价格宏107: {d0.target}")
        frame = session_frame.get_frame(THREAD)
        ent = frame.current_entity if frame else None
        if not ent or ent.get("query") != "夜光亚克力钥匙扣":
            failures.append(f"Turn2 帧未记录当前实体: {ent}")
        else:
            print(f"  帧实体 OK: value={ent.get('value')!r}")

        # ── Turn 3: 指代"它" → 写库存 → money HITL ─────────────────
        decisions = await turn("把它的库存改成142")
        d0 = decisions[0]
        if d0.target_type != "macro" or d0.target.get("id") != 54:
            failures.append(f"Turn3 指代改写后未命中改库存宏54: {d0.target}")
        elif (d0.params or {}).get("query") != "夜光亚克力钥匙扣":
            failures.append(f"Turn3 query 未被指代改写补全: {d0.params}")
        if not delegated or delegated[0]["metadata"].get("macro_id") != 54:
            failures.append(f"Turn3 money 门未委派宏54: {delegated}")
        else:
            print("  money 门委派 OK（宏54 HITL）")
    finally:
        executor._run_agent = orig_run_agent
        session_frame.clear_frame(THREAD)

    print("\n" + ("=" * 40))
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        sys.exit(1)
    print("MULTI-TURN PASS")


asyncio.run(main())
