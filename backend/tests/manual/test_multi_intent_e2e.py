"""Full multi-intent E2E: real decompose + retrieval + routing + sequential
macro execution against the live mall admin (http://127.0.0.1:9002).

    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=xxx \
        .venv/bin/python tests/manual/test_multi_intent_e2e.py

Chains:
  实体词用"夜光亚克力钥匙扣"（goods_id=2, ¥888.00, 库存100）：商城搜索匹配
  sku_name；订阅会员类虚拟商品的编辑页会 500（模板 foreach 崩溃），实体商品正常。

  A. 独立双读: "查一下夜光亚克力钥匙扣，然后查一下订单"
     — both macros really run, in order, with real extracted rows.
  B. 依赖常量: "查夜光亚克力钥匙扣，然后把它的库存改成123"
     — resolver produces new_value=123.0; money macro hits the §16.5 HITL
       delegate (agent boundary captured, everything before it is real).
  C. 依赖链真实求值: "查夜光亚克力钥匙扣的价格，然后把它降10%"
     — field-read macro (查{query}商品价格) extracts a REAL numeric `value`;
       resolver computes new_value=round(value*0.9, 2); the price write
       macro then hits the §16.5 money HITL delegate.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

BASE = "http://127.0.0.1:9002"


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
    from sqlalchemy import select

    from app.core.execution.macro import lifecycle
    from app.core.routing import executor, retriever
    from app.core.routing import router as route_router
    from app.core.routing.schemas import RouteRequest
    from app.core.routing.sync import rebuild_route_index
    from app.infrastructure.database import session_scope
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.infrastructure.drivers.browser import browser_manager
    from app.models.macro import Macro

    await db_resource_manager.initialize(create_tables=False, seed_data=False)

    # 1. Confirm + index the macros this test relies on (real confirm path)
    async with session_scope() as db:
        ids = (
            await db.execute(
                select(Macro.id).where(
                    Macro.project_id == 21,
                    Macro.id.in_([52, 54, 60, 62, 106, 107]),
                    Macro.status == "pending_review",
                )
            )
        ).scalars().all()
    if ids:
        n = await lifecycle.confirm_bulk(list(ids))
        print(f"[e2e] 确认宏: {n}")
    indexed = await rebuild_route_index()
    print(f"[e2e] 路由索引重建: {indexed} 条")

    page = await browser_manager.get_page()
    await login(page)

    failures = []

    async def run_chain(name: str, text: str):
        print(f"\n===== 链 {name}: {text} =====")
        req = RouteRequest(text=text, thread_id=f"e2e-{name}")
        candidates = await retriever.retrieve(text, top_k=20)
        decisions = await route_router.route_many(req, candidates)
        for i, d in enumerate(decisions, 1):
            priv = {k: v for k, v in (d.params or {}).items() if k.startswith("_")}
            pub = {k: v for k, v in (d.params or {}).items() if not k.startswith("_")}
            print(f"  意图{i}: type={d.target_type} target={d.target} params={pub} {priv}")
        return decisions

    # ── 链 A：独立双读，两个宏真实顺序执行 ──────────────────────────
    decisions = await run_chain("A", "查一下夜光亚克力钥匙扣，然后查一下订单")
    kinds = [d.target_type for d in decisions]
    if kinds != ["macro", "macro"]:
        failures.append(f"链A 路由类型异常: {kinds}")
    else:
        executed = []
        orig_run_macro = executor._run_macro

        async def spy_run_macro(tid, decision):
            extracted = await orig_run_macro(tid, decision)
            executed.append((decision.target.get("id"), extracted))
            return extracted

        executor._run_macro = spy_run_macro
        try:
            await executor.execute_many("e2e-A", decisions)
        finally:
            executor._run_macro = orig_run_macro
        print(f"  执行序列: {[(i, bool(e)) for i, e in executed]}")
        if len(executed) != 2 or not all(e for _, e in executed):
            failures.append(f"链A 顺序执行/提取异常: {executed}")
        else:
            ids = [i for i, _ in executed]
            # "查一下X"对路由模型是真实的歧义句：列表宏52(查看{query}商品)与
            # 字段读宏107(查{query}商品价格)都是合理解读，同一文本两次路由
            # 可能漂移；本链断言的是"两个宏真实顺序执行"，意图2必须命中订单宏。
            if ids[0] not in (52, 107) or 62 not in ids:
                failures.append(f"链A 命中宏不符预期(52|107/62): {ids}")

    # ── 链 B：依赖常量 → resolver → money 门（HITL 委派为终点）───────
    decisions = await run_chain("B", "查夜光亚克力钥匙扣，然后把它的库存改成123")
    delegated = []
    orig_run_agent = executor._run_agent

    async def capture_agent(*a, **kw):
        delegated.append(kw)

    executor._run_agent = capture_agent
    seen_params: list[dict] = []
    orig_run_macro = executor._run_macro

    async def spy_macro_b(tid, decision):
        seen_params.append(dict(decision.params or {}))
        return await orig_run_macro(tid, decision)

    executor._run_macro = spy_macro_b
    try:
        await executor.execute_many("e2e-B", decisions)
    finally:
        executor._run_agent = orig_run_agent
        executor._run_macro = orig_run_macro

    money_step = next((p for p in seen_params if "new_value" in p), None)
    print(f"  改库存步参数: {money_step}")
    if money_step is None or money_step.get("new_value") != 123.0:
        failures.append(f"链B resolver 未产出 new_value=123.0: {seen_params}")
    if not delegated or delegated[0]["metadata"].get("macro_id") != 54:
        failures.append(f"链B money 门未按预期委派宏54: {delegated}")
    else:
        print("  money 门委派 OK（宏54 HITL）")

    # ── 链 C：依赖引用真实求值 → resolver → money 门 ─────────────
    decisions = await run_chain("C", "查夜光亚克力钥匙扣的价格，然后把它降10%")
    delegated = []
    executor._run_agent = capture_agent
    executed_c: list[tuple[int, dict, dict | None]] = []

    async def spy_macro_c(tid, decision):
        params_snapshot = dict(decision.params or {})
        extracted = await orig_run_macro(tid, decision)
        executed_c.append((decision.target.get("id"), params_snapshot, extracted))
        return extracted

    executor._run_macro = spy_macro_c
    try:
        await executor.execute_many("e2e-C", decisions)
    finally:
        executor._run_agent = orig_run_agent
        executor._run_macro = orig_run_macro

    read_step = next((e for e in executed_c if e[0] == 107), None)
    write_step = next((e for e in executed_c if e[0] == 60), None)
    if read_step is None or not read_step[2]:
        failures.append(f"链C 字段读宏107未执行或无产出: {executed_c}")
    else:
        raw_value = (read_step[2] or {}).get("value")
        print(f"  价格字段读产出: value={raw_value!r}")
        try:
            price = float(str(raw_value).replace("￥", "").strip())
        except (TypeError, ValueError):
            failures.append(f"链C 字段读 value 非数值: {raw_value!r}")
        else:
            expected = round(price * 0.9, 2)
            if write_step is None or write_step[1].get("new_value") != expected:
                failures.append(
                    f"链C resolver 未产出 new_value={expected}: {executed_c}"
                )
            else:
                print(f"  resolver OK: new_value={expected}")
    if not delegated or delegated[0]["metadata"].get("macro_id") != 60:
        failures.append(f"链C money 门未按预期委派宏60: {delegated}")
    else:
        print("  money 门委派 OK（宏60 HITL）")

    print("\n" + ("=" * 40))
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        sys.exit(1)
    print("ALL CHAINS PASS")


asyncio.run(main())
