"""#4 Batch smoke: every read macro of project 21 against the live mall admin,
engine level. Success = engine completed all steps (empty extraction is OK —
the point is selector grounding, not data presence).

    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=xxx \
        .venv/bin/python tests/manual/batch_smoke_read_macros.py
"""

import asyncio
import os
import sys

from app.utils.yaml import YAMLError

try:
    from playwright.async_api import Error as PlaywrightError
except ImportError:
    PlaywrightError = TimeoutError

_SMOKE_EXCEPTIONS = (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError, YAMLError, PlaywrightError)

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

BASE = "http://127.0.0.1:9002"

# Entity -> a query that exercises the search path. Unknown entities fall
# back to their CJK alias; empty results are fine (selectors still resolve).
QUERY = {
    "goods": "夜光亚克力钥匙扣",
    "order": "订单",
}


async def main() -> None:
    from sqlalchemy import select

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
        macros = (
            await db.execute(
                select(Macro).where(Macro.project_id == 21).order_by(Macro.id)
            )
        ).scalars().all()

    read_macros = [
        m for m in macros if m.name.startswith(("查看", "查{")) and "改{" not in m.name
    ]
    print(f"[smoke] 读宏总数: {len(read_macros)}")

    passed, failed = [], []
    for i, m in enumerate(read_macros, 1):
        try:
            script = MacroScript.from_yaml(m.macro_script)
        except _SMOKE_EXCEPTIONS as e:
            failed.append((m.id, m.name, f"YAML 解析失败: {e}"))
            print(f"[{i}/{len(read_macros)}] #{m.id} {m.name} -> YAML FAIL")
            continue
        query = QUERY.get(m.entity) or m.entity
        try:
            ok, msg, fallback = await MacroEngine.execute(
                thread_id=f"smoke-{m.id}",
                script=script,
                params={"query": query},
            )
        except _SMOKE_EXCEPTIONS as e:
            failed.append((m.id, m.name, f"引擎异常: {type(e).__name__}: {str(e)[:80]}"))
            print(f"[{i}/{len(read_macros)}] #{m.id} {m.name} -> EXC {type(e).__name__}")
            continue
        if ok:
            passed.append((m.id, m.name))
            print(f"[{i}/{len(read_macros)}] #{m.id} {m.name} -> OK")
        else:
            step = (fallback or {}).get("step_number")
            failed.append((m.id, m.name, f"step{step}: {msg[:100]}"))
            print(f"[{i}/{len(read_macros)}] #{m.id} {m.name} -> FAIL step{step}")

    print("\n" + "=" * 50)
    print(f"PASS {len(passed)} / {len(read_macros)}")
    if failed:
        print("失败清单:")
        for mid, name, why in failed:
            print(f"  #{mid} {name}: {why}")


asyncio.run(main())
