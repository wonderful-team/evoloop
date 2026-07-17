"""M3 E2E: generate native macros from surveyed AtlasApps, persist, execute a
safe subset for real, then mark executed ones verified.

SELF-PRESERVATION: this script runs inside iTerm2. NEVER execute macros on
com.googlecode.iterm2 (a "关闭窗口"/"退出" macro would kill the very terminal
hosting this process). iTerm2 is generation-only here. Same care applies to
quit/close-all macros of any app (generated with requires_confirmation — do
not execute them in E2E).

Legs:
  1. Generate menu+field macros for Chrome/iTerm2/WeChat/Lark (counts only).
  2. Execute via MacroEngine:
     - Chrome "打开网址" text=https://example.com (post-verify: address bar readback)
     - Chrome "文件>新建标签页" (post-verify: no exception)
     - WeChat "关于微信" menu macro
     - Lark "关于 Lark" style menu macro
  3. confirm_bulk(executed ids) -> routable.

    .venv/bin/python tests/manual/atlas_native_macro_e2e.py
"""

import asyncio
import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

from app.core.atlas.source.native_factory import generate_for_atlas_app, persist_native_macros
from app.core.atlas.surveyor import MENUBAR_STATE_ID

APPS = [
    ("com.google.Chrome", "Chrome"),
    ("com.googlecode.iterm2", "iTerm2"),
    ("com.tencent.xinWeChat", "WeChat"),
    ("com.bytedance.macos.feishu", "Lark"),
]


async def _load_states(store, bundle):
    summary = await store.get_app_summary(bundle)
    if not summary:
        return None
    states = {}
    for entry in summary.states:
        sid = entry.get("id")
        detail = await store.get_state_detail(bundle, sid)
        if detail:
            states[sid] = {"window_title": detail.window_title, "elements": detail.elements}
    return states


async def main() -> None:
    from app.core.atlas.adapters.sql_store import SQLAtlasStore
    from app.core.atlas.ax_actions import ensure_pid, locate
    from app.core.execution.macro.lifecycle import confirm_bulk
    from app.core.execution.macro.schemas import MacroScript
    from app.core.execution.macro.engine import MacroEngine
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.infrastructure.drivers.macos._workspace import ax_copy_attribute

    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    try:
        store = SQLAtlasStore()
        all_ids: dict[str, list[int]] = {}
        for bundle, name in APPS:
            states = await _load_states(store, bundle)
            if not states:
                print(f"{name:8} 无测绘数据，跳过")
                continue
            cands = generate_for_atlas_app(bundle, name, states)
            menu_n = len([c for c in cands if not c.parameters])
            field_n = len([c for c in cands if c.parameters])
            ids = await persist_native_macros(cands)
            all_ids[bundle] = ids
            confirm_n = len([c for c in cands if c.requires_confirmation])
            print(f"{name:8} 生成 {len(cands)} 宏 (menu={menu_n} field={field_n} 需确认={confirm_n}) -> ids {ids[:3]}...")

        # ── 执行腿 ──
        async def run_macro(macro_id: int, params: dict | None = None):
            from app.core.execution.macro.lifecycle import load_macro

            macro = await load_macro(macro_id)
            script = MacroScript.from_yaml(macro.macro_script)
            return await MacroEngine.execute(thread_id=f"m3-e2e-{macro_id}", script=script, params=params or {})

        executed: list[int] = []

        # Chrome 打开网址 + 地址栏读回
        chrome_ids = all_ids.get("com.google.Chrome", [])
        if chrome_ids:
            from app.core.execution.macro.lifecycle import load_macro

            url_macro = None
            tab_macro = None
            for mid in chrome_ids:
                m = await load_macro(mid)
                if "打开网址" in m.name:
                    url_macro = mid
                if "新标签页" in m.name and "窗口" not in m.name:
                    tab_macro = mid
            if url_macro:
                ok, msg, _ = await run_macro(url_macro, {"text": "https://example.com"})
                print(f"\n[执行] Chrome 打开网址: ok={ok} msg={msg[:80]}")
                from app.core.atlas.ax_actions import find_by_role_label

                pid = ensure_pid("com.google.Chrome")
                el = find_by_role_label(pid, "AXTextField", "地址和搜索栏") if pid else None
                val = ax_copy_attribute(el, "AXValue") if el is not None else None
                print(f"[读回] 地址栏 = {str(val)[:60]!r} -> {'PASS' if val and 'example.com' in str(val) else 'FAIL'}")
                if ok:
                    executed.append(url_macro)
            print(f"[诊断] tab_macro={tab_macro}")
            if tab_macro:
                ok, msg, _ = await run_macro(tab_macro)
                print(f"[执行] Chrome 新建标签页: ok={ok} msg={msg[:80]}")
                if ok:
                    executed.append(tab_macro)

        # WeChat / Lark 各执行一个"关于"菜单宏（iTerm2 永不执行=自残守卫）
        for bundle, key in [("com.tencent.xinWeChat", "关于"), ("com.bytedance.macos.feishu", "关于")]:
            if bundle == "com.googlecode.iterm2":
                continue
            from app.core.execution.macro.lifecycle import load_macro

            for mid in all_ids.get(bundle, []):
                m = await load_macro(mid)
                if key in m.name and not m.requires_confirmation:
                    ok, msg, _ = await run_macro(mid)
                    print(f"[执行] {m.name}: ok={ok} msg={msg[:80]}")
                    if ok:
                        executed.append(mid)
                    break

        if executed:
            n = await confirm_bulk(executed)
            print(f"\n[验证] confirm_bulk: {n} 宏已 verified+routable")
        print(f"\n总生成 {sum(len(v) for v in all_ids.values())} 宏；执行成功 {len(executed)} 个")
    finally:
        await db_resource_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
