"""#8 {{base_url}} placeholder branch: synthesize a macro from a map WITHOUT
extra.base_url, then run it (a) with base_url param -> success, (b) without
-> navigate guard must reject the unresolved placeholder.

    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=xxx \
        .venv/bin/python tests/manual/verify_base_url_placeholder.py
"""

import asyncio
import os
import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

BASE = "http://127.0.0.1:9002"


async def main() -> None:
    from sqlalchemy import select

    from app.core.atlas.source.macro_factory import synthesize
    from app.core.execution.macro.engine import MacroEngine
    from app.core.execution.macro.schemas import MacroScript
    from app.infrastructure.database import session_scope
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.infrastructure.drivers.browser import browser_manager
    from app.models.app_map import AppMap

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
        am = (
            await db.execute(
                select(AppMap).where(
                    AppMap.project_id == 21,
                    AppMap.entity == "goods",
                    AppMap.status == "active",
                )
            )
        ).scalars().first()

    entity_map = {
        "entity": am.entity,
        "aliases": am.aliases,
        "routes": am.routes,
        "actions": am.actions,
        "elements": am.elements,
        "db_tables": am.db_tables,
        "extra": {},  # strip base_url -> placeholder branch
        "map_version": am.map_version,
    }
    result = synthesize(entity_map)
    cand = next(c for c in result.candidates if c.name == "查看{query}商品")
    param_names = [p["name"] for p in cand.parameters]
    script = MacroScript(steps=cand.macro_script)
    first_url = script.steps[0].payload.get("url")
    print(f"[base_url] url={first_url} params={param_names}")
    assert "{{base_url}}" in first_url, "占位分支未触发"
    assert "base_url" in param_names, "base_url 参数未声明"

    failures = []

    ok, msg, fb = await MacroEngine.execute(
        thread_id="verify-baseurl-ok",
        script=script,
        params={"query": "夜光亚克力钥匙扣", "base_url": BASE},
    )
    print(f"[base_url] 传参执行: ok={ok} msg={msg[:60]}")
    if not ok:
        failures.append(f"传 base_url 仍失败: {msg[:100]}")

    ok2, msg2, fb2 = await MacroEngine.execute(
        thread_id="verify-baseurl-missing",
        script=script,
        params={"query": "夜光亚克力钥匙扣"},
    )
    print(f"[base_url] 缺参执行: ok={ok2} msg={msg2[:60]}")
    if ok2:
        failures.append("缺 base_url 应被 navigate 守卫拦截却成功")
    elif "{{" not in msg2 and "未解析" not in msg2:
        failures.append(f"缺参失败原因非未解析守卫: {msg2[:100]}")

    print("\n" + ("=" * 40))
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        sys.exit(1)
    print("BASE_URL PLACEHOLDER PASS（传参可跑/缺参被守卫拦截）")


asyncio.run(main())
