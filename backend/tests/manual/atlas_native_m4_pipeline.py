"""M4 pipeline: bulk-verify safe native macros -> rebuild route index ->
routing corpus (30/app, NO execution) -> safe execution subset.

Safety: execution leg whitelists only innocuous macros and NEVER touches
iTerm2 window/session lifecycle (this script runs inside iTerm2).

    .venv/bin/python tests/manual/atlas_native_m4_pipeline.py
"""

import asyncio
import sys
import uuid

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

APPS = {
    # bundle: (生成宏名前缀, 语料用展示名)
    "com.google.Chrome": ("Chrome", "Chrome"),
    "com.googlecode.iterm2": ("iTerm2", "iTerm"),
    "com.tencent.xinWeChat": ("WeChat", "微信"),
    "com.bytedance.macos.feishu": ("Lark", "飞书"),
}

# Execution leg: only these leaf keywords may really run (ui-tier, non-confirm).
EXEC_WHITELIST = {
    "com.google.Chrome": ["新标签页"],
    "com.googlecode.iterm2": ["New Tab", "新标签页"],
    "com.tencent.xinWeChat": ["关于微信"],
    "com.bytedance.macos.feishu": ["关于飞书"],
}


def _leaf(name: str, app_name: str) -> str:
    n = name
    if n.startswith(app_name):
        n = n[len(app_name):].strip()
    return n.split(">")[-1].strip()


async def main() -> None:
    from sqlalchemy import select, update

    from app.core.execution.macro.schemas import MacroScript
    from app.core.execution.macro.engine import MacroEngine
    from app.core.routing import retriever
    from app.core.routing.router import route_many
    from app.core.routing.schemas import RouteRequest
    from app.core.routing.sync import rebuild_route_index
    from app.infrastructure.database import session_scope
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.models.macro import Macro

    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    try:
        # 1. 批量验证安全子集（ui 层且无需确认）
        async with session_scope() as db:
            result = await db.execute(
                update(Macro)
                .where(
                    Macro.namespace == "native_macos",
                    Macro.status == "pending_review",
                    Macro.risk_tier == "ui",
                    Macro.requires_confirmation.is_(False),
                )
                .values(status="verified", is_active=True)
            )
            verified = result.rowcount
        print(f"[批量验证] ui 层免确认宏 verified: {verified}")

        # 2. 重建路由索引
        await rebuild_route_index()
        print("[索引] rebuild_route_index 完成")

        # 3. 装载可路由宏，构建语料
        async with session_scope() as db:
            rows = (
                (await db.execute(select(Macro).where(Macro.namespace == "native_macos", Macro.is_active.is_(True))))
                .scalars()
                .all()
            )
        by_bundle: dict[str, list] = {b: [] for b in APPS}
        for m in rows:
            for b, (gen_name, _disp) in APPS.items():
                if m.name.startswith(gen_name + " "):
                    by_bundle[b].append(m)
                    break

        corpus: list[tuple[str, str, int, str]] = []  # (utterance, bundle, macro_id, kind)
        for bundle, (gen_name, app_name) in APPS.items():
            macros = by_bundle[bundle]
            menu_macros = [m for m in macros if not m.parameters]
            menu_macros.sort(key=lambda m: m.name)
            step = max(1, len(menu_macros) // 10)
            sampled = menu_macros[::step][:10]
            for m in sampled:
                leaf = _leaf(m.name, gen_name)
                if not leaf:
                    continue
                corpus.append((leaf, bundle, m.id, "bare"))
                corpus.append((f"{app_name}{leaf}", bundle, m.id, "qualified"))
                corpus.append((f"帮我{leaf}", bundle, m.id, "polite"))
            field_macros = [m for m in macros if m.parameters]
            for m in field_macros[:2]:
                if "网址" in m.name or "打开" in m.name:
                    corpus.append(("打开 example.com", bundle, m.id, "field"))
                    corpus.append(("访问 example.com", bundle, m.id, "field"))
        print(f"[语料] {len(corpus)} 条")

        # 4. 路由语料（不执行）
        stats = {b: {"hit": 0, "miss": 0, "clarify": 0, "other": 0, "misses": []} for b in APPS}
        kind_stats: dict[str, dict[str, int]] = {}
        thread_id = f"m4-corpus-{uuid.uuid4().hex[:8]}"
        for i, (text, bundle, expect_id, kind) in enumerate(corpus):
            candidates = await retriever.retrieve(text, top_k=20)
            decisions = await route_many(RouteRequest(text=text, thread_id=f"{thread_id}-{i}"), candidates)
            d = decisions[0] if decisions else None
            if d is None:
                stats[bundle]["other"] += 1
                continue
            ks = kind_stats.setdefault(kind, {"hit": 0, "miss": 0, "clarify": 0, "other": 0})
            if d.status == "clarify":
                stats[bundle]["clarify"] += 1
                ks["clarify"] += 1
                continue
            target = d.target or {}
            got_id = target.get("id") if target.get("type") == "macro" else None
            if got_id == expect_id:
                stats[bundle]["hit"] += 1
                ks["hit"] += 1
            else:
                stats[bundle]["miss"] += 1
                ks["miss"] += 1
                got_name = next((c.name for c in (d.candidates or []) if c.id == f"macro:{got_id}"), str(got_id))
                stats[bundle]["misses"].append((text, got_name))

        print("\n── 路由语料结果（hit / miss / clarify / other）──")
        for bundle, (_gen, app_name) in APPS.items():
            s = stats[bundle]
            total = s["hit"] + s["miss"] + s["clarify"] + s["other"]
            print(f"{app_name:8} {s['hit']}/{total}  (miss={s['miss']} clarify={s['clarify']} other={s['other']})")
            for text, got in s["misses"][:5]:
                print(f"   miss: {text!r} -> {got[:60]}")
        print("\n── 按语句类型 ──")
        for kind, ks in kind_stats.items():
            total = sum(ks.values())
            print(f"{kind:10} {ks['hit']}/{total} (miss={ks['miss']} clarify={ks['clarify']} other={ks['other']})")

        # 5. 安全执行子集
        print("\n── 执行子集（白名单，真实执行）──")
        for bundle, keywords in EXEC_WHITELIST.items():
            macros = by_bundle[bundle]
            done = False
            for m in macros:
                if m.requires_confirmation or m.parameters:
                    continue
                leaf = _leaf(m.name, APPS[bundle][0])
                if any(k in leaf for k in keywords):
                    script = MacroScript.from_yaml(m.macro_script)
                    ok, msg, _ = await MacroEngine.execute(
                        thread_id=f"m4-exec-{m.id}", script=script, params={}
                    )
                    print(f"  {m.name}: ok={ok} {msg[:60]}")
                    done = True
                    break
            if not done:
                print(f"  {APPS[bundle][1]}: 白名单内无可执行宏，跳过")
    finally:
        await db_resource_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
