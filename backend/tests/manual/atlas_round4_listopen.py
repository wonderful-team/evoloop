"""Round-4: generate the new list_open navigation macros (打开X列表).

Re-synthesizes goods/order from the existing AppMaps (no re-survey), upserts
in place, and ACTIVATES the new navigation macros (verified/is_active) since
their grounding is identical to the already-verified list_view siblings.

    .venv/bin/python tests/manual/atlas_round4_listopen.py
"""

import asyncio
import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")


async def main() -> None:
    from sqlalchemy import select

    from app.core.atlas.source.macro_factory import synthesize
    from app.core.execution.macro.lifecycle import _macro_to_yaml
    from app.infrastructure.database import session_scope
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.models.app_map import AppMap
    from app.models.macro import Macro

    await db_resource_manager.initialize(create_tables=False, seed_data=False)

    async with session_scope() as db:
        maps = (
            await db.execute(
                select(AppMap).where(
                    AppMap.project_id == 21,
                    AppMap.status == "active",
                    AppMap.entity.in_(["goods", "order"]),
                )
            )
        ).scalars().all()

        for am in maps:
            entity_map = {
                "entity": am.entity,
                "aliases": am.aliases,
                "routes": am.routes,
                "actions": am.actions,
                "elements": am.elements,
                "db_tables": am.db_tables,
                "extra": am.extra,
                "map_version": am.map_version,
            }
            result = synthesize(entity_map)

            existing = (
                await db.execute(
                    select(Macro).where(
                        Macro.project_id == 21, Macro.entity == am.entity
                    )
                )
            ).scalars().all()
            by_name = {m.name: m for m in existing}

            updated = inserted = 0
            for c in result.candidates:
                hit = by_name.get(c.name)
                if hit is not None:
                    hit.macro_script = _macro_to_yaml(c)
                    hit.trigger_patterns = c.trigger_patterns
                    hit.parameters = c.parameters
                    hit.description = c.description
                    db.add(hit)
                    updated += 1
                    continue
                macro = Macro(
                    app_map_id=am.id,
                    entity=am.entity,
                    name=c.name,
                    description=c.description,
                    trigger_patterns=c.trigger_patterns,
                    parameters=c.parameters,
                    macro_script=_macro_to_yaml(c),
                    risk_tier=c.risk_tier,
                    requires_confirmation=c.requires_confirmation,
                    status="verified" if c.name.startswith("打开") else "pending_review",
                    is_active=c.name.startswith("打开"),
                    app_map_version=c.app_map_version,
                    project_id=21,
                    member_id=0,
                )
                db.add(macro)
                await db.flush()
                print(f"[round4] NEW: {c.name} -> id={macro.id} active={macro.is_active}")
                inserted += 1
            print(f"[round4] {am.entity}: {updated} updated, {inserted} inserted")


asyncio.run(main())
