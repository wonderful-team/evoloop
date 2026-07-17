"""#3 Self-healing policy gate, real machine: corrupt macro 52's search-input
selector, run through MacroService (the production orchestrator), assert the
policy gate + advisor suggestions on a REAL engine failure.

    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=xxx \
        .venv/bin/python tests/manual/verify_self_healing_real.py
"""

import asyncio
import os
import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

BASE = "http://127.0.0.1:9002"


async def main() -> None:
    from app.core.execution.macro.schemas import MacroScript
    from app.core.execution.macro.service import MacroService
    from app.infrastructure.database import session_scope
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.infrastructure.drivers.browser import browser_manager
    from app.models.macro import Macro

    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    # Standalone process: mirror server/worker startup (main.py:71,
    # run_worker.py:75) so the @event_register advisor actually instantiates.
    from app.core.events.discovery import auto_discover_handlers

    auto_discover_handlers()
    page = await browser_manager.get_page()
    await page.goto(f"{BASE}/shop.html", wait_until="load", timeout=30000)
    await page.wait_for_timeout(1500)
    if "login" in page.url:
        await page.fill("[name='username']", os.environ["MALL_ADMIN_USER"])
        await page.fill("[name='password']", os.environ["MALL_ADMIN_PASS"])
        await page.click("[lay-filter='login']")
        await page.wait_for_timeout(3000)

    async with session_scope() as db:
        m = await db.get(Macro, 52)
        yaml_str = m.macro_script

    broken_yaml = yaml_str.replace("[name=''search_text'']", "[name=''search_text_broken'']")
    assert broken_yaml != yaml_str, "corruption no-op"
    script = MacroScript.from_yaml(broken_yaml)

    failures = []

    # 1. Healing ENABLED (global default True) -> fallback_required + suggestions
    res = await MacroService.run(
        "verify-heal-on", script, params={"query": "夜光亚克力钥匙扣"}
    )
    print(
        f"[heal-on] success={res.success} status={res.status} "
        f"allow={res.allow_self_healing} suggestions={len(res.suggestions or [])}"
    )
    if res.success:
        failures.append("损坏选择器却执行成功？！")
    if res.status != "fallback_required":
        failures.append(f"status != fallback_required: {res.status}")
    if not res.allow_self_healing:
        failures.append("allow_self_healing 应为 True")
    if not res.suggestions:
        failures.append("advisor 未产出建议")
    else:
        print(f"[heal-on] 建议前80字: {res.suggestions[0][:80]!r}")

    # 2. Healing DISABLED via execution override -> blocked with reason
    res2 = await MacroService.run(
        "verify-heal-off",
        MacroScript.from_yaml(broken_yaml),
        params={"query": "夜光亚克力钥匙扣", "_allow_self_healing": False},
    )
    print(
        f"[heal-off] success={res2.success} allow={res2.allow_self_healing} "
        f"reason={res2.healing_disabled_reason} source={res2.healing_disabled_source}"
    )
    if res2.success:
        failures.append("损坏选择器却执行成功？！(off)")
    if res2.allow_self_healing:
        failures.append("执行级禁用时 allow_self_healing 应为 False")
    if res2.healing_disabled_source != "execution":
        failures.append(f"禁用来源应为 execution: {res2.healing_disabled_source}")

    print("\n" + ("=" * 40))
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        sys.exit(1)
    print("SELF-HEALING POLICY PASS（真机失败→策略门→建议事件 全链）")


asyncio.run(main())
