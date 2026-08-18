"""Macro background tasks (Huey)."""

from __future__ import annotations

import logging

from app.infrastructure.queue.factory import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="macro_synthesize_from_app_map")
async def synthesize_macros_task(
    app_map_id: int,
    project_id: int,
    member_id: int = 0,
):
    """Run the template factory against one AppMap and persist candidates.

    Triggered explicitly (generate_macros_from_app_map tool / generate-macros
    API) — never auto-fired by APP_MAP_CREATED.
    """
    from app.core.atlas.source import persistence as app_map_store
    from app.core.atlas.source.macro_factory import synthesize
    from app.core.execution.macro import lifecycle

    app_map = await app_map_store.get_app_map(app_map_id)
    if app_map is None:
        logger.warning("[Macro] synthesize: app_map %s not found", app_map_id)
        return {"candidates": 0, "error": "app_map not found"}

    entity_map = {
        "entity": app_map.entity,
        "aliases": app_map.aliases,
        "routes": app_map.routes,
        "actions": app_map.actions,
        "elements": app_map.elements,
        "db_tables": app_map.db_tables,
        "extra": app_map.extra,
        "map_version": app_map.map_version,
    }
    result = synthesize(entity_map)

    ids = await lifecycle.persist_candidates(
        app_map_id=app_map_id,
        entity=app_map.entity,
        project_id=project_id,
        candidates=result.candidates,
        member_id=member_id,
    )

    if result.gaps:
        logger.info("[Macro] coverage gaps for %s: %s", app_map.entity, result.gaps)
    if result.validation_errors:
        logger.warning("[Macro] validation errors: %s", result.validation_errors)

    return {
        "candidates": len(ids),
        "macro_ids": ids,
        "gaps": result.gaps,
        "validation_errors": result.validation_errors,
    }


@shared_task(name="native_macro_maintenance")
async def native_macro_maintenance_task(apps: list[tuple[str, str]] | None = None) -> list[dict]:
    """Resurvey -> regenerate (replace) -> reindex for the configured apps.

    Triggered explicitly (maintenance API / frontend entry) — never
    auto-fired on a schedule (scanning launches apps, which would disturb
    the user; desktop UI macros update on demand instead).
    """
    from app.core.execution.macro.maintenance import native_macro_maintenance

    return await native_macro_maintenance(apps=apps)
