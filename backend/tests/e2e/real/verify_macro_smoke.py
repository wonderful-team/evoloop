"""Real-machine smoke: login -> replay one list_view macro -> two-stage write dry-run.

源自 2.0 设计期验证脚本 `tests/manual/smoke_atlas_macro.py`，迁移至
`tests/e2e/real/` 作为 AppMap→模板宏→真实网页执行链路的冒烟验证。

Usage:
    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=xxx SMOKE_PROJECT_ID=21 \\
        .venv/bin/python tests/e2e/real/verify_macro_smoke.py

Env:
    MALL_ADMIN_USER / MALL_ADMIN_PASS  商城后台登录凭据（必填）
    SMOKE_PROJECT_ID                   目标项目 ID（默认 21）
    SMOKE_QUERY                        查看宏查询词（默认 PVC线圈本）

- 查看类: full MacroEngine replay of "查看{query}商品" (query=PVC线圈本), asserts
  the extracted rows text is non-empty.
- 改价类: runs ONLY steps 1-7 of the two-stage write macro (search -> extract id
  -> open edit page) and asserts the edit page loaded for the right goods id.
  The save click is NEVER executed in smoke (money tier).
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

BASE = os.environ.get("SMOKE_BASE", "http://127.0.0.1:9002")
GOODS_QUERY = os.environ.get("SMOKE_QUERY", "PVC线圈本")
PROJECT_ID = int(os.environ.get("SMOKE_PROJECT_ID", "21"))


async def login(page) -> None:
    user = os.environ["MALL_ADMIN_USER"]
    password = os.environ["MALL_ADMIN_PASS"]
    await page.goto(f"{BASE}/shop.html", wait_until="load", timeout=30000)
    await page.wait_for_timeout(1500)
    if "login" not in page.url:
        print(f"[smoke] 已是登录态: {page.url}")
        return
    await page.fill("[name='username']", user)
    await page.fill("[name='password']", password)
    await page.click("[lay-filter='login']")
    await page.wait_for_timeout(3000)
    if "login" in page.url:
        raise RuntimeError(f"登录失败，仍停留在 {page.url}")
    print(f"[smoke] 登录成功: {page.url}")


async def main() -> None:
    from sqlalchemy import select

    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.infrastructure.drivers.browser import browser_manager

    await db_resource_manager.initialize(create_tables=False, seed_data=False)

    page = await browser_manager.get_page()
    await login(page)

    from app.core.learning.macro.engine import MacroEngine
    from app.core.learning.macro.schemas import MacroScript
    from app.infrastructure.database import session_scope
    from app.models.macro import Macro

    async with session_scope() as db:
        view_macro = (
            (
                await db.execute(
                    select(Macro).where(
                        Macro.project_id == PROJECT_ID,
                        Macro.entity == "goods",
                        Macro.risk_tier == "ui",
                        Macro.status == "pending_review",
                    )
                )
            )
            .scalars()
            .first()
        )
        write_macro = (
            (
                await db.execute(
                    select(Macro).where(
                        Macro.project_id == PROJECT_ID,
                        Macro.entity == "goods",
                        Macro.risk_tier == "money",
                        Macro.status == "pending_review",
                    )
                )
            )
            .scalars()
            .first()
        )

    assert view_macro and write_macro, "goods 查看/改价宏缺失"

    # ── 1. 查看类完整回放 ─────────────────────────────────────────────
    script = MacroScript.from_yaml(view_macro.macro_script)
    extracted: dict = {}
    ok, msg, _ = await MacroEngine.execute(
        "smoke-view",
        script,
        params={"query": GOODS_QUERY},
        extracted_data=extracted,
    )
    rows = str(extracted.get("rows", ""))
    print(f"[smoke] 查看宏 ok={ok} msg={msg[:120]}")
    print(f"[smoke] 提取 rows 长度={len(rows)} 前200字: {rows[:200]!r}")
    assert ok, f"查看宏执行失败: {msg}"
    assert GOODS_QUERY[:2] in rows or len(rows) > 20, "rows 为空或不含查询商品"

    # ── 2. 改价类两段式 dry-run（仅步骤 1-7，不点保存）─────────────────
    wscript = MacroScript.from_yaml(write_macro.macro_script)
    stage1 = [s for s in wscript.steps if s.step_number <= 7]
    extracted2: dict = {}
    ok2, msg2, _ = await MacroEngine.execute_steps(
        "smoke-write-dry",
        steps=stage1,
        params={"query": GOODS_QUERY, "new_value": "0"},
        extracted_data=extracted2,
    )
    entity_id = extracted2.get("entity_id")
    print(f"[smoke] 两段式 dry-run ok={ok2} msg={msg2[:120]} entity_id={entity_id}")
    print(f"[smoke] 编辑页 URL: {page.url}")
    assert ok2, f"两段式执行失败: {msg2}"
    assert entity_id and str(entity_id).isdigit(), f"未提取到数字 id: {entity_id!r}"
    assert f"id={entity_id}" in page.url, "编辑页未按提取 id 打开"
    title = await page.title()
    body_text = (await page.inner_text("body"))[:400]
    assert GOODS_QUERY[:2] in body_text or "编辑" in body_text, "编辑页内容异常"
    print(f"[smoke] 编辑页标题: {title}")
    print("[smoke] ALL PASS（保存步骤未执行，属预期）")


asyncio.run(main())
