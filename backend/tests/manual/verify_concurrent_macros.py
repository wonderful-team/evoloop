"""#10 Concurrency probe: two macros on the shared browser page at once
(asyncio.gather). Whatever happens IS the finding — success means the
engine serializes safely; failure/wrong data documents the interference.

    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=xxx \
        .venv/bin/python tests/manual/verify_concurrent_macros.py
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

BASE = "http://127.0.0.1:9002"


async def main() -> None:
    from app.core.execution.macro.engine import MacroEngine
    from app.core.execution.macro.schemas import MacroScript
    from app.infrastructure.database import session_scope
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.infrastructure.drivers.browser import browser_manager
    from app.models.macro import Macro

    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    page = await browser_manager.get_page()
    await page.goto(f"{BASE}/shop.html", wait_until="load", timeout=30000)
    await page.wait_for_timeout(1500)
    if "login" in page.url:
        await page.fill("[name='username']", os.environ["MALL_ADMIN_USER"])
        await page.fill("[name='password']", os.environ["MALL_ADMIN_PASS"])
        await page.click("[lay-filter='login']")
        await page.wait_for_timeout(3000)

    async with session_scope() as db:
        m52 = MacroScript.from_yaml((await db.get(Macro, 52)).macro_script)
        m62 = MacroScript.from_yaml((await db.get(Macro, 62)).macro_script)

    async def run(tag, script, query):
        t0 = time.monotonic()
        ok, msg, fb = await MacroEngine.execute(
            thread_id=f"conc-{tag}", script=script, params={"query": query}
        )
        return tag, ok, msg[:60], (fb or {}).get("step_number"), round(time.monotonic() - t0, 1)

    print("[conc] 基线：串行各跑一次")
    for tag, script, q in [("A", m52, "夜光亚克力钥匙扣"), ("B", m62, "订单")]:
        r = await run(tag, script, q)
        print(f"  串行 {r}")

    print("[conc] 并发：asyncio.gather 同页双宏")
    results = await asyncio.gather(
        run("A", m52, "夜光亚克力钥匙扣"),
        run("B", m62, "订单"),
    )
    for r in results:
        print(f"  并发 {r}")

    both_ok = all(r[1] for r in results)
    print("\n" + ("=" * 40))
    print(f"并发双成功: {both_ok}（False=存在页面级干扰，需执行锁）")


asyncio.run(main())
