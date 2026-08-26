"""Native macro maintenance: periodic resurvey -> regenerate -> replace -> reindex.

Owned by the macro module (macro table writes must go through the macro DAO).
Atlas provides the survey (UI element capture) and the generation factory;
this module orchestrates the pass and persists via the macro lifecycle.

Cadence task lives in app/core/execution/macro/tasks.py (Huey).
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import select

from app.core.atlas.source.native_factory import generate_for_atlas_app
from app.core.atlas.surveyor import AtlasSurveyor, SurveyPolicy
from app.core.execution.macro.lifecycle import persist_native_macros

logger = logging.getLogger(__name__)

# Guardrail: sane upper bound per app (Chrome hits ~170; >500 means the
# filters regressed — keep data, but scream in logs).
MAX_MACROS_PER_APP = 500

# Default survey set — TODO: 原为 "high-frequency pilot"（Chrome/iTerm2/微信/飞书），
# 因固定试点集合意义有限且定时扫描会启动应用打扰用户，已清空。
# 扫描目标改为完全由调用方显式指定（API apps 参数 / EVO_NATIVE_SURVEY_APPS）。
DEFAULT_APPS: list[tuple[str, str]] = []


def configured_apps() -> list[tuple[str, str]]:
    raw = os.environ.get("EVO_NATIVE_SURVEY_APPS", "").strip()
    if not raw:
        return DEFAULT_APPS
    out: list[tuple[str, str]] = []
    for part in raw.split(","):
        if ":" in part:
            bundle, name = part.split(":", 1)
            out.append((bundle.strip(), name.strip()))
    return out or DEFAULT_APPS


async def resurvey_and_regen(
    bundle_id: str,
    app_name: str,
    surveyor: AtlasSurveyor | None = None,
    policy: SurveyPolicy | None = None,
) -> dict:
    """One app's maintenance pass. Read-only survey (no exploration clicks —
    this runs unattended)."""
    surveyor = surveyor or AtlasSurveyor()
    needs = await surveyor.needs_resurvey(bundle_id)
    if not needs:
        return {"bundle_id": bundle_id, "action": "skip_fresh"}

    result = await surveyor.survey_app(
        bundle_id, app_name=app_name, policy=policy or SurveyPolicy(explore=False)
    )
    if result.error or result.app is None:
        return {
            "bundle_id": bundle_id,
            "action": "survey_failed",
            "error": result.error,
        }

    states = {
        sid: {
            "window_title": s.window_title,
            "elements": [e.model_dump() for e in s.elements],
        }
        for sid, s in result.app.states.items()
    }
    candidates = generate_for_atlas_app(bundle_id, app_name, states)
    if len(candidates) > MAX_MACROS_PER_APP:
        logger.warning(
            f"[native-maintenance] {bundle_id} 生成 {len(candidates)} 宏 "
            f"> {MAX_MACROS_PER_APP} 护栏，过滤规则可能退化"
        )
    ids = await persist_native_macros(candidates)
    await verify_safe_native_macros()
    return {
        "bundle_id": bundle_id,
        "action": "regenerated",
        "states": len(result.app.states),
        "tier": result.coverage.tier,
        "macros": len(ids),
        "menu_reachable_pct": result.coverage.menu_reachable_pct,
    }


async def verify_safe_native_macros() -> int:
    """Bulk-verify the safe subset (ui tier + no confirmation) — same policy
    as the M4 pipeline; keeps regeneration routable without human review.

    Uses the macro module's confirm_bulk inside the caller's transaction so
    the lifecycle event is published and the L0 / navigation caches refresh.
    """
    from app.core.execution.macro.lifecycle import confirm_bulk
    from app.infrastructure.database import session_scope
    from app.models.macro import Macro

    async with session_scope() as db:
        stmt = select(Macro.id).where(
            Macro.namespace == "native_macos",
            Macro.status == "pending_review",
            Macro.risk_tier == "ui",
            Macro.requires_confirmation.is_(False),
        )
        ids = list((await db.execute(stmt)).scalars().all())
        if not ids:
            return 0
        return await confirm_bulk(ids, db=db)


async def native_macro_maintenance(apps: list[tuple[str, str]] | None = None) -> list[dict]:
    """Full pass over the configured set; reindex once if anything changed."""
    results: list[dict] = []
    for bundle_id, app_name in apps or configured_apps():
        try:
            results.append(await resurvey_and_regen(bundle_id, app_name))
        except Exception as e:
            logger.exception(f"[native-maintenance] {bundle_id} failed: {e}")
            results.append({"bundle_id": bundle_id, "action": "error", "error": str(e)})

    logger.info(f"[native-maintenance] done: {results}")
    return results
