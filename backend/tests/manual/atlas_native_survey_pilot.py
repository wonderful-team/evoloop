"""M2 pilot: survey Calculator / System Settings / Music into the Atlas store.

Verifies acceptance criteria (design doc §3 + v0.3 R6):
- menu tree node reachability >= 90%
- 3 pilot AtlasApp persisted (states incl. __menubar__, transitions)
- state fingerprint stable across re-surveys (same sig_* ids)
- needs_resurvey() returns False right after survey

    .venv/bin/python tests/manual/atlas_native_survey_pilot.py
"""

import asyncio
import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

from app.core.atlas.surveyor import MENUBAR_STATE_ID, AtlasSurveyor, SurveyPolicy

PILOTS = [
    ("com.apple.calculator", "Calculator", SurveyPolicy(explore=False)),
    ("com.apple.systempreferences", "System Settings", SurveyPolicy(explore=True, max_clicks=12, click_settle_sec=0.9)),
    ("com.apple.Music", "Music", SurveyPolicy(explore=True, max_clicks=8, click_settle_sec=0.9)),
]


async def main() -> None:
    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    try:
        sv = AtlasSurveyor()
        for bundle, name, policy in PILOTS:
            r = await sv.survey_app(bundle, app_name=name, policy=policy)
            if r.error:
                print(f"{name:18} ERROR {r.error}")
                continue
            w = r.coverage.window
            m = r.coverage.menubar
            print(
                f"{name:18} tier={r.coverage.tier} states={len(r.app.states)} trans={r.transitions_found} "
                f"menu_reach={r.coverage.menu_reachable_pct}% "
                f"win(named_inter={w['interactive_named']},named%={w['named_pct']},zero%={w['zero_bounds_pct']}) "
                f"menu(items={m['menu']})"
            )

        print("\n── 落库验证 ──")
        for bundle, name, _ in PILOTS:
            summary = await sv.store.get_app_summary(bundle)
            if not summary:
                print(f"{name:18} 未入库!")
                continue
            menubar = await sv.store.get_state_detail(bundle, MENUBAR_STATE_ID)
            menu_named = len([e for e in (menubar.elements if menubar else []) if e.get("label")])
            transitions = await sv.store.get_transitions_summary(bundle)
            sig_states = [s for s in summary.states if str(s.get("id", "")).startswith("sig_")]
            print(
                f"{name:18} states={summary.state_count} (sig={len(sig_states)}) "
                f"menubar项={menu_named} transitions={len(transitions)}"
            )

        print("\n── 重测稳定性（state_id 应完全一致）──")
        for bundle, name, policy in PILOTS:
            before = await sv.store.get_app_summary(bundle)
            ids1 = sorted(s.get("id") for s in before.states) if before else []
            r2 = await sv.survey_app(bundle, app_name=name, policy=SurveyPolicy(explore=False))
            ids2 = sorted(sid for sid in r2.app.states.keys())
            stable = all(sid in ids1 for sid in ids2 if sid.startswith("sig_"))
            resurvey = await sv.needs_resurvey(bundle)
            print(
                f"{name:18} sig_ids={ids2} 全部已存在={stable} needs_resurvey={resurvey}"
            )
    finally:
        await db_resource_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
