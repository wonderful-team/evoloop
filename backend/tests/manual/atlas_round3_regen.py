"""Round-3 re-survey: fix the order list-table element (server-rendered table,
not a layui widget) and regenerate goods/order macros IN PLACE (ids stable).

    .venv/bin/python tests/manual/atlas_round3_regen.py

What it does:
1. order AppMap: replace the `order_list` id element with the surveyor-exact
   css selector `table.order-list-table tbody` (the runtime page has no
   lay-id='order_list'; the采集 had read the JS container div id).
2. Re-synthesize goods + order entity maps through the current template
   factory (now with css-table support and the crud_field_read sibling).
3. Update existing macros in place by (entity, name) — preserving ids,
   status, and confirmations. Insert genuinely new candidates as
   pending_review.
"""

import asyncio
import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

ORDER_TABLE_CSS = "table.order-list-table tbody"


async def main() -> None:
    from sqlalchemy import select

    from app.core.atlas.source.macro_factory import synthesize
    from app.core.atlas.source.macro_factory.synthesizer import _check_candidate
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
            if am.entity == "order":
                els = [el for el in am.elements if el.get("name") != "order_list"]
                els.append(
                    {
                        "name": ORDER_TABLE_CSS,
                        "page": "app/shop/view/order/lists.html",
                        "line": 172,
                        "binds": "订单列表表格 行数据容器",
                        "selector_type": "css",
                    }
                )
                am.elements = els
                db.add(am)
                print("[round3] order map: order_list(id) -> css tbody")
            if am.entity == "goods":
                # Controllers read input('goods_id') on GET; editGoodsStock is
                # JSON-only — its rendered page is the editGoods form.
                # NOTE: JSON columns need REASSIGNMENT (am.routes = routes) —
                # in-place dict mutation is invisible to SQLAlchemy's dirty
                # tracking and the fix would silently never be persisted.
                routes = [dict(r) for r in am.routes]
                for r in routes:
                    if r.get("source_action") == "editGoods":
                        r["id_param"] = "goods_id"
                    elif r.get("source_action") in ("editGoodsStock", "batchSet"):
                        # JSON/batch endpoints: single-entity page is the
                        # editGoods form (has [name=price]/[name=goods_stock]).
                        r["id_param"] = "goods_id"
                        r["page_url"] = "shop/goods/editgoods"
                am.routes = routes
                # price/goods_stock live in the "价格库存" layui tab (inactive
                # panels are display:none; input actions need visibility).
                has_tab_el = any(
                    el.get("selector_type") == "text" and el.get("name") == "价格库存"
                    for el in am.elements
                )
                if not has_tab_el:
                    am.elements = [
                        *am.elements,
                        {
                            "name": "价格库存",
                            "page": "app/shop/view/goods/edit_goods.html",
                            "line": 40,
                            "binds": "编辑页页签 价格库存",
                            "selector_type": "text",
                        },
                    ]
                for el in am.elements:
                    if el.get("name") in ("price", "goods_stock") and el.get("selector_type") == "name":
                        el["tab"] = "价格库存"
                db.add(am)
                print("[round3] goods routes: id_param=goods_id, editGoodsStock/batchSet page_url -> editgoods; price/goods_stock tab=价格库存")

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
            problems = []
            for c in result.candidates:
                problems.extend(_check_candidate(c, entity_map))
            if problems:
                print(f"[round3] {am.entity} validation problems: {problems}")

            existing = (
                await db.execute(
                    select(Macro).where(
                        Macro.project_id == 21, Macro.entity == am.entity
                    )
                )
            ).scalars().all()
            by_name = {}
            for m in existing:
                by_name.setdefault(m.name, m)

            from app.core.execution.macro.lifecycle import _macro_to_yaml

            updated = inserted = 0
            for c in result.candidates:
                hit = by_name.get(c.name)
                if hit is not None:
                    hit.macro_script = _macro_to_yaml(c)
                    hit.trigger_patterns = c.trigger_patterns
                    hit.parameters = c.parameters
                    hit.description = c.description
                    hit.risk_tier = c.risk_tier
                    hit.requires_confirmation = c.requires_confirmation
                    hit.app_map_version = c.app_map_version
                    db.add(hit)
                    updated += 1
                else:
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
                        status="pending_review",
                        is_active=False,
                        app_map_version=c.app_map_version,
                        project_id=21,
                        member_id=0,
                    )
                    db.add(macro)
                    await db.flush()
                    print(f"[round3] NEW candidate: {c.name} -> id={macro.id}")
                    inserted += 1
            print(
                f"[round3] {am.entity}: {updated} updated, {inserted} inserted, "
                f"gaps={len(result.gaps)}"
            )


asyncio.run(main())
