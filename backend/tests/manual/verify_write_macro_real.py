"""#1 Real-write verification: macro 54 (改{query}商品库存) full 10 steps,
engine level (bypassing the voice money gate), against goods_id=2.

    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=xxx \
        .venv/bin/python tests/manual/verify_write_macro_real.py

Flow: backup -> write stock=142 -> assert DB -> write stock=100 (restore,
same macro) -> assert DB -> assert price/name untouched.
"""

import asyncio
import os
import subprocess
import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

BASE = "http://127.0.0.1:9002"
GOODS_ID = 2


def db_stock() -> tuple[float, float]:
    out = subprocess.run(
        [
            "mysql", "-h127.0.0.1", "-uroot", "-padmin888", "b2c_mall", "-N", "-e",
            f"SELECT g.goods_stock, (SELECT s.stock FROM goods_sku s WHERE s.goods_id=g.goods_id LIMIT 1) FROM goods g WHERE g.goods_id={GOODS_ID}",
        ],
        capture_output=True, text=True, check=True,
    ).stdout.strip().split("\t")
    return float(out[0]), float(out[1])


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
    assert "login" not in page.url, "登录失败"

    async with session_scope() as db:
        m = await db.get(Macro, 54)
        script = MacroScript.from_yaml(m.macro_script)

    before = db_stock()
    print(f"[write] 备份: goods_stock={before[0]} sku_stock={before[1]}")
    assert before == (100.0, 100.0), f"前置库存异常: {before}"

    failures = []
    for target in (142, 100):
        ok, msg, fallback = await MacroEngine.execute(
            thread_id=f"verify-write-{target}",
            script=script,
            params={"query": "夜光亚克力钥匙扣", "new_value": target},
        )
        # layui saves via AJAX after the click; the engine returns before the
        # POST lands — give it a moment before reading the DB.
        await page.wait_for_timeout(2500)
        after = db_stock()
        print(f"[write] new_value={target} -> engine ok={ok} msg={msg[:80]} DB={after}")
        if not ok:
            failures.append(f"引擎执行失败(target={target}): {msg[:120]} fb={fallback}")
        elif after != (float(target), float(target)):
            failures.append(f"DB 未生效(target={target}): {after}")

    final = subprocess.run(
        [
            "mysql", "-h127.0.0.1", "-uroot", "-padmin888", "b2c_mall", "-N", "-e",
            f"SELECT price, goods_name, goods_state, is_delete FROM goods WHERE goods_id={GOODS_ID}",
        ],
        capture_output=True, text=True, check=True,
    ).stdout.strip().split("\t")
    print(f"[write] 副作用检查: price={final[0]} name={final[1]} state={final[2]} del={final[3]}")
    if final[0] != "888.00" or final[1] != "夜光亚克力钥匙扣" or final[2] != "1" or final[3] != "0":
        failures.append(f"保存副作用: {final}")

    print("\n" + ("=" * 40))
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        sys.exit(1)
    print("REAL WRITE PASS（写入+恢复均经宏真实执行）")


asyncio.run(main())
