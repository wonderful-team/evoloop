"""
Atlas-Native maintenance: periodic resurvey -> regenerate -> replace -> reindex.

Junk-macro philosophy (design review 2026-07-16): garbage in the macro table
comes from (a) generation rules evolving after data was written, (b) surveyed
content drifting. A periodic "find and delete junk" task treats the symptom;
regeneration IS the cleanup — persist replaces each app's macro batch
wholesale, so rules evolution and drift both converge on every pass.

Cadence task lives in app/core/atlas/tasks.py (Huey).
"""

from __future__ import annotations

import logging
import os

from app.core.atlas.source.native_factory import generate_for_atlas_app, persist_native_macros
from app.core.atlas.surveyor import MENUBAR_STATE_ID, AtlasSurveyor, SurveyPolicy

logger = logging.getLogger(__name__)

# Guardrail: sane upper bound per app (Chrome hits ~170; >500 means the
# filters regressed — keep data, but scream in logs).
MAX_MACROS_PER_APP = 500

# Default survey set = the high-frequency pilot (design v0.4). Override with
# env EVO_NATIVE_SURVEY_APPS="bundle:Name,bundle:Name".
DEFAULT_APPS: list[tuple[str, str]] = [
    ("com.google.Chrome", "Chrome"),
    ("com.googlecode.iterm2", "iTerm2"),
    ("com.tencent.xinWeChat", "WeChat"),
    ("com.bytedance.macos.feishu", "Lark"),
]


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
        return {"bundle_id": bundle_id, "action": "survey_failed", "error": result.error}

    states = {
        sid: {"window_title": s.window_title, "elements": [e.model_dump() for e in s.elements]}
        for sid, s in result.app.states.items()
    }
    candidates = generate_for_atlas_app(bundle_id, app_name, states)
    if len(candidates) > MAX_MACROS_PER_APP:
        logger.warning(
            f"[atlas-maintenance] {bundle_id} 生成 {len(candidates)} 宏 "
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
    as the M4 pipeline; keeps regeneration routable without human review."""
    from sqlalchemy import update

    from app.infrastructure.database import session_scope
    from app.models.macro import Macro

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
        return result.rowcount or 0


async def native_atlas_maintenance(apps: list[tuple[str, str]] | None = None) -> list[dict]:
    """Full pass over the configured set; reindex once if anything changed."""
    results: list[dict] = []
    for bundle_id, app_name in apps or configured_apps():
        try:
            results.append(await resurvey_and_regen(bundle_id, app_name))
        except Exception as e:
            logger.error(f"[atlas-maintenance] {bundle_id} failed: {e}")
            results.append({"bundle_id": bundle_id, "action": "error", "error": str(e)})

    logger.info(f"[atlas-maintenance] done: {results}")
    return results
