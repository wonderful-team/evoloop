#7b ASR-noise robustness: homophone/filler/number-word mutations of the
# hit-rate suite, measuring whether the route LLM still understands intent.
# Same harness as verify_routing_hitrate.py — routing layer only (does the
# intent survive noise), not execution.
#
#     .venv/bin/python tests/manual/verify_routing_noise.py
#
# Mutation types: 同音字(亚克力→压力克, 钥匙→要是, 库存→裤存, 价格→价各,
# 订单→定单, 售价→售假), 语气词混入(那个/嗯/呃), 数字文字化(50→五十),
# 连接词(然后→然候).

import asyncio
import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

CASES = [
    # ── 查看商品 → 52（实体词同音错，无字段词）────────────────
    ("查一下夜光压力克钥匙扣", {52}, "同音:亚克力→压力克"),
    ("查一下夜光亚克力要是扣", {52}, "同音:钥匙→要是"),
    ("帮我看看夜光亚克力钥匙扣那个", {52, 106, 107}, "语气尾巴"),
    # ── 查库存 → 106 ──────────────────────────────────────
    ("夜光压力克钥匙扣还有多少裤存", {106}, "同音:库存→裤存"),
    ("查一下夜光亚克力钥匙扣的裤存", {106}, "同音:裤存"),
    ("钥匙扣裤存够吗", {106, 52}, "同音:裤存"),
    ("夜光亚克力钥匙扣剩多少件嗯", {106}, "语气词"),
    # ── 查价格 → 107 ──────────────────────────────────────
    ("夜光压力克钥匙扣多少钱", {107}, "同音:实体"),
    ("查一下夜光亚克力钥匙扣的价各", {107}, "同音:价格→价各"),
    ("钥匙扣卖多少钱呃", {107}, "语气词"),
    ("夜光亚克力钥匙扣的售假是多少", {107}, "同音:售价→售假"),
    # ── 改库存 → 54（写方向，HITL 兜底仍在）──────────────────
    ("把夜光亚克力钥匙扣的裤存改成五十", {54}, "裤存+数字文字"),
    ("钥匙扣裤存调到两百", {54}, "裤存+数字文字"),
    ("修改夜光压力克钥匙扣的库存为88", {54}, "同音:实体"),
    # ── 改价格 → 60 ──────────────────────────────────────
    ("把夜光亚克力钥匙扣的价各改成六十六", {60}, "价各+数字文字"),
    ("钥匙扣价格调到九十九", {60}, "数字文字"),
    ("把钥匙扣的价格降成59", {60}, "降成"),
    # ── 查看订单 → 62 ──────────────────────────────────────
    ("查一下定单", {62}, "同音:订单→定单"),
    ("看看最近的订但", {62}, "同音:订单→订但"),
    ("定单列表给我看看", {62}, "同音:定单"),
    # ── 无关 → 不应命中宏 ────────────────────────────────
    ("今天天气怎摸样", None, "同音:怎么样→怎摸样"),
    ("帮我写个周爆", None, "同音:周报→周爆"),
]

CATEGORY = {
    "查看商品": (0, 3), "查库存": (3, 7), "查价格": (7, 11),
    "改库存": (11, 14), "改价格": (14, 17), "查看订单": (17, 20),
    "无关": (20, 23),
}


async def main() -> None:
    from app.core.routing import retriever
    from app.core.routing import router as route_router
    from app.core.routing.schemas import RouteRequest
    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=False, seed_data=False)

    results = []
    for phrase, expected, mutation in CASES:
        cands = await retriever.retrieve(phrase, top_k=20)
        d = await route_router.route(RouteRequest(text=phrase, thread_id="noise"), cands)
        got = d.target.get("id") if d.target_type == "macro" else None
        if expected is None:
            ok = d.target_type != "macro" or got not in {52, 54, 60, 62, 106, 107}
        else:
            ok = got in expected
        results.append((phrase, expected, got, d.target_type, mutation, ok))
        print(f"{'✓' if ok else '✗'} [{mutation}] {phrase} -> {d.target_type}:{got}")

    print("\n" + "=" * 46)
    total_hits = sum(1 for r in results if r[5])
    print(f"噪声命中率: {total_hits}/{len(CASES)} = {total_hits / len(CASES):.0%}")
    for cat, (lo, hi) in CATEGORY.items():
        sub = results[lo:hi]
        h = sum(1 for r in sub if r[5])
        print(f"  {cat}: {h}/{len(sub)}")
    misses = [r for r in results if not r[5]]
    if misses:
        print("未命中明细:")
        for phrase, expected, got, tt, mutation, _ in misses:
            print(f"  [{mutation}] {phrase} 期望{expected} 实得{tt}:{got}")


asyncio.run(main())
