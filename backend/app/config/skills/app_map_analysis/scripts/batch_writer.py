#!/usr/bin/env python3
"""Batch-write AppMap records from a collector JSON file.

Usage:
    uv run python app/config/skills/app_map_analysis/scripts/batch_write_app_maps.py \\
        --project-id 121 --input /tmp/appmap_extracted.json

The JSON must have the format produced by the AppMap collector script:
    {
      "entity_name": {
        "actions": [{"name": "...", "kind": "read|write", "risk_tier": "...",
                     "controller": "...", "line": N, "business_rule": "...",
                     "touches_tables": [...], "set_fields": [...], "pk": "..."}],
        "elements": [{"name": "...", "page": "...", "line": N,
                      "binds": "...", "selector_type": "..."}],
        "routes": [{"name": "...", "url": "...", "method": "GET|POST|...",
                    "source_action": "..."}],
        "db_tables": [{"table": "...", "pk": "...", "cols": [...]}],
        "aliases": ["..."],
        "platform": "web|admin|..."
      },
      ...
    }
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import logging

from app.core.atlas.source.persistence import save_app_map
from app.core.execution.macro.tasks import synthesize_macros_task as _wrapped_task

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("batch_writer")

# Unwrap @shared_task decorator once at module level
_raw = getattr(_wrapped_task, "func", _wrapped_task)
if not inspect.iscoroutinefunction(_raw):
    for _cell in getattr(_raw, "__closure__", None) or []:
        if inspect.iscoroutinefunction(_cell.cell_contents):
            _raw = _cell.cell_contents
            break


async def _gen_macros(app_map_id, project_id, member_id):
    return await _raw(app_map_id=app_map_id, project_id=project_id, member_id=member_id)


async def batch_write(
    project_id: int,
    entities: dict,
    member_id: int = 0,
) -> dict:
    """Batch-write AppMap records and generate macros.

    Returns ``{"written": int, "skipped": int, "failed": int, "macros_generated": int}``.
    """
    written = 0
    skipped = 0
    failed = 0
    macros_generated = 0

    for entity_name, data in sorted(entities.items()):
        try:
            app_map_id, version, created = await save_app_map(
                project_id=project_id,
                entity=entity_name,
                platform=data.get("platform", "web"),
                aliases=data.get("aliases", [entity_name]),
                routes=data.get("routes", []),
                actions=data.get("actions", []),
                elements=data.get("elements", []),
                db_tables=data.get("db_tables", []),
                extra=data.get("extra"),
                member_id=member_id,
            )

            if created:
                written += 1
            else:
                skipped += 1

            try:
                result = await _gen_macros(
                    app_map_id=app_map_id,
                    project_id=project_id,
                    member_id=member_id,
                )
                macros_generated += result.get("candidates", 0)
            except Exception as exc:
                logger.warning("  [MACRO] %s macro generation failed: %s", entity_name, exc)

        except Exception as exc:
            failed += 1
            logger.error("  [FAIL]  %s: %s", entity_name, exc)

    logger.info(
        "Batch complete: %d written, %d skipped (unchanged), %d failed, %d macros generated",
        written, skipped, failed, macros_generated,
    )
    return {
        "written": written,
        "skipped": skipped,
        "failed": failed,
        "macros_generated": macros_generated,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-write AppMap records")
    parser.add_argument("--project-id", type=int, required=True, help="Target project ID")
    parser.add_argument("--input", type=str, required=True, help="Path to collector JSON")
    parser.add_argument("--member-id", type=int, default=0, help="Member ID (default 0)")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        entities: dict = json.load(f)

    if not entities:
        logger.warning("Empty entity data — nothing to write")
        print(json.dumps({"status": "ok", "total": 0, "written": 0, "skipped": 0, "failed": 0, "macros_generated": 0}))
        return

    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=False, seed_data=False)

    from app.core.evocloud import evocloud_manager
    from app.core.identity import identity_service

    evocloud_manager.initialize()
    login = await evocloud_manager.login("preterchan", "hellomylife")
    await identity_service.set_token(login["token"], login.get("refresh_token", ""))
    member_id = args.member_id or (await identity_service.get_member_id(login["token"]))

    logger.info("Starting batch write for %d entities (project=%s)", len(entities), args.project_id)

    result = await batch_write(project_id=args.project_id, entities=entities, member_id=member_id)
    print(json.dumps({"status": "ok" if not result["failed"] else "partial", **result}))

    await db_resource_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
