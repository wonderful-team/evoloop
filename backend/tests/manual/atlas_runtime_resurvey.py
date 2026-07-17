"""Runtime DOM re-survey (round-5): the source-level survey over-claimed
elements that do not exist on the live pages (83/103 read macros failed
smoke, mostly step3 search input). This script visits every entity's list
page, dumps the RUNTIME DOM, and repairs the AppMap at map level:

  - search input: map element absent at runtime -> replace with the best
    runtime input (name/placeholder heuristics); no candidate -> mark
    `runtime_absent` (templates skip it -> honest coverage gap).
  - search button: same, against runtime [lay-filter] values.
  - result table: absent -> first runtime [lay-id] container, else a plain
    table as a surveyor-exact css selector.

Then re-synthesizes + upserts macros IN PLACE per entity and deactivates
macros whose grounding disappeared. Re-run batch_smoke_read_macros.py after.

    MALL_ADMIN_USER=admin MALL_ADMIN_PASS=xxx \
        .venv/bin/python tests/manual/atlas_runtime_resurvey.py
"""

import asyncio
import os
import re
import sys

try:
    from playwright.async_api import Error as PlaywrightError
except ImportError:
    PlaywrightError = TimeoutError

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

BASE = "http://127.0.0.1:9002"

_DUMP_JS = """() => ({
  inputs: [...document.querySelectorAll('input')].map(i => ({
    name: i.name || '', placeholder: i.placeholder || '', type: i.type || '',
    visible: !!(i.offsetWidth || i.offsetHeight)
  })),
  layFilters: [...new Set([...document.querySelectorAll('[lay-filter]')].map(e => e.getAttribute('lay-filter')))],
  layIds: [...document.querySelectorAll('[lay-id]')].map(e => ({id: e.getAttribute('lay-id'), hasTable: !!e.querySelector('.layui-table')})).filter(x => x.id).filter((x, i, arr) => arr.findIndex(y => y.id === x.id) === i),
  tables: [...document.querySelectorAll('table')].map(t => ({
    cls: t.className || '', id: t.id || '', inLayui: !!t.closest('.layui-table')
  }))
})"""

_TEXT_TYPES = {"", "text", "search"}
_SEARCH_NAME_RE = re.compile(r"search|keyword|query|key", re.I)
_SEARCH_PH_RE = re.compile(r"搜索|关键字|关键词|名称|编号|标题")
_SEARCH_NAME_SOFT_RE = re.compile(r"name|title|no\.?$|code", re.I)
_FILTER_RE = re.compile(r"search|query|so$|find", re.I)


def _pick_search_input(inputs: list[dict]) -> dict | None:
    best: tuple[int, dict] | None = None
    for i in inputs:
        if not i["visible"] or i["type"].lower() not in _TEXT_TYPES:
            continue
        score = 0
        if _SEARCH_NAME_RE.search(i["name"]):
            score = 3
        elif _SEARCH_PH_RE.search(i["placeholder"]):
            score = 2
        elif _SEARCH_NAME_SOFT_RE.search(i["name"]):
            score = 1
        if score and (best is None or score > best[0]):
            best = (score, i)
    return best[1] if best else None


async def _present(page, selector: str) -> bool:
    from playwright.async_api import Error as PlaywrightError

    try:
        return await page.query_selector(selector) is not None
    except PlaywrightError:
        return False


async def main() -> None:
    from sqlalchemy import select

    from app.core.atlas.source.macro_factory import synthesize, templates
    from app.core.execution.macro.lifecycle import _macro_to_yaml
    from app.infrastructure.database import session_scope
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.infrastructure.drivers.browser import browser_manager
    from app.models.app_map import AppMap
    from app.models.macro import Macro

    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    page = await browser_manager.get_page()
    await page.goto(f"{BASE}/shop.html", wait_until="load", timeout=30000)
    await page.wait_for_timeout(1500)
    if "login" in page.url:
        await page.fill("[name='username']", os.environ["MALL_ADMIN_USER"])
        await page.fill("[name='password']", os.environ["MALL_ADMIN_PASS"])
        await page.click("[lay-filter='login']")
        await page.wait_for_timeout(3000)
    assert "login" not in page.url, "登录失败"

    stats = {"search_fixed": 0, "search_absent": 0, "table_fixed": 0,
             "table_absent": 0, "deactivated": 0, "skipped": 0}

    async with session_scope() as db:
        maps = (
            await db.execute(
                select(AppMap).where(
                    AppMap.project_id == 21, AppMap.status == "active"
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
            # Canonical read/ui macro's step-1 URL is the page that matters.
            macro = (
                await db.execute(
                    select(Macro).where(
                        Macro.project_id == 21,
                        Macro.entity == am.entity,
                        Macro.name.like("查看%"),
                        Macro.name.not_like("%（%"),
                    )
                )
            ).scalars().first()
            url = None
            if macro is not None:
                m = re.search(r"url:\s*(\S+)", macro.macro_script)
                url = m.group(1) if m and m.group(1) != "null" else None
            if not url or "{{" in (url or ""):
                print(f"[resurvey] {am.entity}: 无列表页 URL，跳过")
                stats["skipped"] += 1
                continue

            try:
                await page.goto(url, wait_until="load", timeout=30000)
                await page.wait_for_timeout(1500)
                dom = await page.evaluate(_DUMP_JS)
            except (PlaywrightError, asyncio.TimeoutError, OSError, RuntimeError, ValueError) as e:
                print(f"[resurvey] {am.entity}: 页面访问失败 {e}，跳过")
                stats["skipped"] += 1
                continue
            if "login" in page.url:
                print(f"[resurvey] {am.entity}: 登录态丢失，终止")
                break

            elements = [dict(el) for el in am.elements]
            changed = False

            # ── search input ───────────────────────────────────────
            search_el = templates._find_search_input(entity_map)
            if search_el is not None and not await _present(
                page, templates._selector(search_el)
            ):
                cand = _pick_search_input(dom["inputs"])
                idx = next(
                    (
                        i
                        for i, e in enumerate(elements)
                        if e.get("name") == search_el.get("name")
                        and e.get("page") == search_el.get("page")
                    ),
                    None,
                )
                if cand is not None:
                    if cand["name"]:
                        new_el = {
                            "name": cand["name"],
                            "page": search_el.get("page"),
                            "line": search_el.get("line"),
                            "binds": search_el.get("binds", ""),
                            "selector_type": "name",
                            "runtime_fixed": True,
                        }
                    else:
                        new_el = {
                            "name": f"[placeholder='{cand['placeholder']}']",
                            "page": search_el.get("page"),
                            "line": search_el.get("line"),
                            "binds": search_el.get("binds", ""),
                            "selector_type": "css",
                            "runtime_fixed": True,
                        }
                    if idx is not None:
                        elements[idx] = new_el
                    else:
                        elements.append(new_el)
                    stats["search_fixed"] += 1
                    print(f"[resurvey] {am.entity}: 搜索框 {search_el['name']} -> {new_el['name']}")
                else:
                    for e in elements:
                        if e.get("name") == search_el.get("name"):
                            e["runtime_absent"] = True
                    stats["search_absent"] += 1
                    print(f"[resurvey] {am.entity}: 搜索框 {search_el['name']} 运行时不存在且无替代 -> absent")
                changed = True
                entity_map["elements"] = elements

            # ── search button ──────────────────────────────────────
            btn_el = templates._find_search_button(entity_map)
            if btn_el is not None and not await _present(
                page, templates._selector(btn_el)
            ):
                cand_f = next(
                    (f for f in dom["layFilters"] if _FILTER_RE.search(f or "")),
                    None,
                )
                for e in elements:
                    if e.get("name") == btn_el.get("name") and e.get("page") == btn_el.get("page"):
                        if cand_f:
                            e["name"] = cand_f
                            e["selector_type"] = "lay-filter"
                            e["runtime_fixed"] = True
                            print(f"[resurvey] {am.entity}: 搜索按钮 -> lay-filter={cand_f}")
                        else:
                            e["runtime_absent"] = True
                            print(f"[resurvey] {am.entity}: 搜索按钮运行时不存在 -> absent")
                        changed = True
                entity_map["elements"] = elements

            # ── result table ───────────────────────────────────────
            table_el = templates._find_element(
                entity_map, ("表格", "列表", "table", "结果", "清单", "list")
            )
            revived = False
            if table_el is None:
                # All surveyed table elements are marked runtime_absent — try
                # to REVIVE one with a runtime alternative (hasTable lay-id
                # or a specific-class server-rendered table).
                best_lay = next((x for x in dom["layIds"] if x["hasTable"]), None)
                generic = {"layui-table", "layui-form", "layui-table-view"}
                plain = None
                for t in dom["tables"]:
                    tokens = [x for x in t["cls"].split() if x and x not in generic]
                    if tokens:
                        plain = f"table.{tokens[0]} tbody"
                        break
                new_name = best_lay["id"] if best_lay else plain
                new_type = "id" if best_lay else "css"
                if new_name:
                    for e in elements:
                        if e.get("runtime_absent") and any(
                            k in f"{e.get('name', '')} {e.get('binds', '')}".lower()
                            for k in ("表格", "列表", "table", "结果", "清单", "list")
                        ):
                            e.update({
                                "name": new_name,
                                "selector_type": new_type,
                                "runtime_fixed": True,
                            })
                            e.pop("runtime_absent", None)
                            entity_map["elements"] = elements
                            table_el = e
                            changed = True
                            revived = True
                            stats["table_fixed"] += 1
                            print(f"[resurvey] {am.entity}: 表格复活 -> {new_name}")
                            break
            if table_el is not None and not revived:
                if table_el.get("selector_type") == "id":
                    probe = f"[lay-id='{table_el['name']}']"
                else:
                    probe = templates._selector(table_el)
                # name='' is a previous bad repair (empty lay-id) — force
                # redo; a repaired lay-id whose container has no .layui-table
                # (e.g. lay-id='1' internals) is also a bad pick.
                lay_entry = next(
                    (x for x in dom["layIds"] if x["id"] == table_el.get("name")),
                    None,
                )
                stale_pick = (
                    table_el.get("selector_type") == "id"
                    and table_el.get("runtime_fixed")
                    and (lay_entry is None or not lay_entry["hasTable"])
                )
                if (
                    not table_el.get("name")
                    or stale_pick
                    or not await _present(page, probe)
                ):
                    best_lay = next(
                        (x for x in dom["layIds"] if x["hasTable"]), None
                    )
                    new_table = None
                    if best_lay is not None:
                        new_table = {
                            "name": best_lay["id"],
                            "page": table_el.get("page"),
                            "line": table_el.get("line"),
                            "binds": table_el.get("binds", ""),
                            "selector_type": "id",
                            "runtime_fixed": True,
                        }
                    else:
                        # Server-rendered table (like order lists): a real
                        # <table> with a SPECIFIC class token (generic
                        # layui-table/layui-form classes don't count).
                        generic = {"layui-table", "layui-form", "layui-table-view"}
                        plain = None
                        for t in dom["tables"]:
                            tokens = [x for x in t["cls"].split() if x and x not in generic]
                            if tokens:
                                plain = f"table.{tokens[0]} tbody"
                                break
                        if plain is not None:
                            new_table = {
                                "name": plain,
                                "page": table_el.get("page"),
                                "line": table_el.get("line"),
                                "binds": table_el.get("binds", ""),
                                "selector_type": "css",
                                "runtime_fixed": True,
                            }
                    for e in elements:
                        if e.get("name") == table_el.get("name") and e.get("page") == table_el.get("page"):
                            if new_table is not None:
                                e.update(new_table)
                                stats["table_fixed"] += 1
                                print(f"[resurvey] {am.entity}: 表格 -> {new_table['name']}")
                            else:
                                e["runtime_absent"] = True
                                stats["table_absent"] += 1
                                print(f"[resurvey] {am.entity}: 表格运行时不存在且无替代 -> absent")
                            changed = True
                    entity_map["elements"] = elements

            if changed:
                am.elements = elements
                db.add(am)

            # ── re-synthesize + upsert + deactivate ungrounded ─────
            result = synthesize(entity_map)
            produced = {c.name: c for c in result.candidates}
            existing = (
                await db.execute(
                    select(Macro).where(
                        Macro.project_id == 21, Macro.entity == am.entity
                    )
                )
            ).scalars().all()
            for m in existing:
                c = produced.get(m.name)
                if c is not None:
                    m.macro_script = _macro_to_yaml(c)
                    m.trigger_patterns = c.trigger_patterns
                    m.parameters = c.parameters
                    m.description = c.description
                    db.add(m)
                elif m.name.startswith(("查看", "打开", "查")):
                    if m.is_active:
                        stats["deactivated"] += 1
                    m.status = "pending_review"
                    m.is_active = False
                    db.add(m)

    print(f"\n[resurvey] 统计: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
