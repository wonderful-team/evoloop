"""Real-model verification of multi-intent decomposition (LM Studio qwen3-4b).

Battery of compound / single / tricky instructions run against the real route
LLM. Prints every raw output for inspection and asserts structural quality.
Run:
    .venv/bin/python tests/manual/test_decompose_real_model.py
"""

import asyncio
import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

# NOTE: decompose and resolver modules have been removed (dead code after voice architecture refactor)

CASES = [
    # (text, expect_intents, expect_dep, note)
    ("查一下铰链的价格", 1, None, "单意图无连接词，启发式应直接跳过"),
    ("查一下订阅会员的价格，再把它的价格降10%", 2, 1, "经典依赖链"),
    ("查铰链价格，然后查螺丝库存", 2, None, "独立双意图"),
    (
        "先看看万年历的价格，然后帮我把它改成88",
        2,
        1,
        "依赖（改为绝对值，无表达式也行）",
    ),
    ("查商品A的价格，然后降5毛", 2, 1, "相对降价，期望减法式"),
    ("查一下订单列表，顺便把会员张三的余额改成500", 2, None, "独立（改余额是绝对值）"),
    ("查铰链价格，然后查螺丝库存，再把铰链降价10%", 3, 1, "三意图混合依赖"),
    ("查一下铰链的价格然后告诉我", 1, None, "连接词陷阱：实为单意图"),
    ("check the price of the hinge and then reduce it by 10%", 2, 1, "英文依赖链"),
    ("把铰链价格降10%", 1, None, "看似依赖但无前序，单意图"),
]

passed = failed = 0


async def run_case(text: str, expect_n: int, expect_dep, note: str) -> None:
    global passed, failed
    intents = await decompose(text)
    n = len(intents) if intents else 1
    ok = n == expect_n
    dep_ok = True
    expr_ok = True
    dep_info = ""
    if intents and expect_dep is not None:
        dep = next((i.depends_on for i in intents if i.depends_on), None)
        dep_ok = dep == expect_dep
        exprs = next((i.param_exprs for i in intents if i.param_exprs), {})
        if exprs:
            for expr in exprs.values():
                try:
                    resolve_expression(
                        expr, {1: {"value": 100.0, "price": 100.0, "stock": 100.0}}
                    )
                except Exception as e:  # noqa: BLE001 — 评估脚本，打印一切失败
                    expr_ok = False
                    dep_info += f" expr解析失败({expr!r}: {e})"
        dep_info = f" dep={dep} exprs={exprs}"
    status = "PASS" if (ok and dep_ok and expr_ok) else "FAIL"
    if status == "PASS":
        passed += 1
    else:
        failed += 1
    detail = (
        " | ".join(f"[{i.text}](dep={i.depends_on})" for i in intents)
        if intents
        else "(单意图)"
    )
    print(
        f"{status} n={n}/{expect_n} {note}\n     输入: {text}\n     输出: {detail}{dep_info}"
    )


async def main() -> None:
    for text, n, dep, note in CASES:
        await run_case(text, n, dep, note)
    print(f"\n==== {passed} passed, {failed} failed ====")
    sys.exit(1 if failed else 0)


asyncio.run(main())
