#7 Phrasing hit-rate: ~30 real-user phrasings against the real route stack
# (retrieve + route LLM). Measurement, not pass/fail — per-category hit rate.
#
#     .venv/bin/python tests/manual/verify_routing_hitrate.py

import asyncio
import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

# (phrase, expected macro id set) — None = should NOT hit any goods/order macro
CASES = [
    # 查看商品/列表 → 52
    ("查一下夜光亚克力钥匙扣", {52}),
    ("帮我看看夜光亚克力钥匙扣这个商品", {52, 106, 107}),
    ("查询商品列表", {52}),
    ("夜光亚克力钥匙扣的详细信息", {52, 106, 107}),
    # 查库存 → 106
    ("夜光亚克力钥匙扣还有多少库存", {106}),
    ("查一下夜光亚克力钥匙扣的库存", {106}),
    ("钥匙扣库存够吗", {106, 52}),
    ("夜光亚克力钥匙扣剩多少件", {106}),
    # 查价格 → 107
    ("夜光亚克力钥匙扣多少钱", {107}),
    ("查一下夜光亚克力钥匙扣的价格", {107}),
    ("钥匙扣卖多少钱", {107}),
    ("夜光亚克力钥匙扣的售价是多少", {107}),
    # 改库存 → 54
    ("把夜光亚克力钥匙扣的库存改成50", {54}),
    ("钥匙扣库存调到200", {54}),
    ("修改夜光亚克力钥匙扣的库存为88", {54}),
    # 改价格 → 60
    ("把夜光亚克力钥匙扣的价格改成66", {60}),
    ("钥匙扣价格调到99", {60}),
    ("修改夜光亚克力钥匙扣的售价", {60}),
    # 查看订单 → 62
    ("查一下订单", {62}),
    ("看看最近的订单", {62}),
    ("订单列表给我看看", {62}),
    ("查询订单信息", {62}),
    # 无关 → 不应命中商品/订单宏
    ("今天天气怎么样", None),
    ("帮我写个周报", None),
    ("讲个笑话", None),
]


async def main() -> None:
    from app.core.routing import retriever
    from app.core.routing import router as route_router
    from app.core.routing.schemas import RouteRequest
    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=False, seed_data=False)

    hits = misses = 0
    miss_rows = []
    for phrase, expected in CASES:
        cands = await retriever.retrieve(phrase, top_k=20)
        d = await route_router.route(RouteRequest(text=phrase, thread_id="hitrate"), cands)
        got = d.target.get("id") if d.target_type == "macro" else None
        if expected is None:
            ok = d.target_type != "macro" or got not in {52, 54, 60, 62, 106, 107}
        else:
            ok = got in expected
        mark = "✓" if ok else "✗"
        if ok:
            hits += 1
        else:
            misses += 1
            miss_rows.append((phrase, expected, d.target_type, got))
        print(f"{mark} {phrase} -> {d.target_type}:{got} (期望 {expected})")

    print("\n" + "=" * 40)
    print(f"命中率: {hits}/{len(CASES)} = {hits / len(CASES):.0%}")
    if miss_rows:
        print("未命中:")
        for phrase, expected, tt, got in miss_rows:
            print(f"  {phrase} 期望{expected} 实得{tt}:{got}")


asyncio.run(main())
