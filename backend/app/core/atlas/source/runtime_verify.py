"""Runtime verification for AppMap elements (v3.1 core).

Validates that the macro target_selectors derived from an AppMap actually
resolve on the live page; repairs absent ones with runtime heuristics or marks
them ``runtime_absent`` so the template factory skips them (honest coverage gap).

Inherits the algorithm proven in 2.0's ``atlas_runtime_resurvey.py`` manual
script (DOM dump, name/placeholder/lay-filter scoring, table revival, macro
re-synthesis, deactivation of ungrounded macros) and turns it into a
programmable training-pipeline phase.

Chain verified here:
    AppMap.elements[].name (source symbol)
      -> template/selector rule -> macro.target_selector (runtime selector)
      -> runtime verify: does the selector resolve on the live page?
      -> repair element + re-synthesize, or mark runtime_absent.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select

from app.core.atlas.source import macro_factory
from app.core.execution.macro import macro_to_yaml
from app.infrastructure.database import session_scope
from app.infrastructure.database.resource_manager import db_resource_manager
from app.infrastructure.drivers.browser import browser_manager
from app.models.app_map import AppMap
from app.models.macro import Macro

logger = logging.getLogger(__name__)

# DOM dump script: inputs, lay-filter values, lay-id tables, plain tables.
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

# Generic layui class tokens that never identify a specific result table.
_GENERIC_CLASSES = {"layui-table", "layui-form", "layui-table-view"}

# Element keyword families used to locate the search input / button / table.
_SEARCH_INPUT_KEYS = ("搜索框", "输入框", "筛选")
_SEARCH_BUTTON_KEYS = ("搜索", "search", "筛选", "查询")
_TABLE_KEYS = ("表格", "列表", "table", "结果", "清单", "list")


def _pick_search_input(inputs: list[dict]) -> dict | None:
    """Highest-scoring visible text-ish input that looks like a search box."""
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


def _element_selector(el: dict) -> str:
    """Runtime selector for an AppMap element (mirror templates._selector)."""
    from app.core.atlas.source.macro_factory import templates

    return templates._selector(el)


def _upsert_element(elements: list[dict], new_el: dict, idx: int | None) -> None:
    if idx is not None:
        elements[idx] = new_el
    else:
        elements.append(new_el)


def _find_index(elements: list[dict], name: str, page: str | None) -> int | None:
    for i, e in enumerate(elements):
        if e.get("name") == name and e.get("page") == page:
            return i
    return None


def _repair_search_input(
    elements: list[dict], search_el: dict, dom: dict
) -> tuple[bool, bool]:
    """Repair an absent search input. Returns (repaired, still_absent)."""
    cand = _pick_search_input(dom["inputs"])
    if cand is None:
        return False, True
    page = search_el.get("page")
    if cand["name"]:
        new_el = {
            "name": cand["name"],
            "page": page,
            "line": search_el.get("line"),
            "binds": search_el.get("binds", ""),
            "selector_type": "name",
            "runtime_fixed": True,
        }
    else:
        new_el = {
            "name": f"[placeholder='{cand['placeholder']}']",
            "page": page,
            "line": search_el.get("line"),
            "binds": search_el.get("binds", ""),
            "selector_type": "css",
            "runtime_fixed": True,
        }
    idx = _find_index(elements, search_el.get("name"), page)
    _upsert_element(elements, new_el, idx)
    return True, False


def _repair_search_button(elements: list[dict], btn_el: dict, dom: dict) -> None:
    """Repair an absent search button in place (or mark runtime_absent)."""
    cand_f = next((f for f in dom["layFilters"] if _FILTER_RE.search(f or "")), None)
    for e in elements:
        if e.get("name") == btn_el.get("name") and e.get("page") == btn_el.get("page"):
            if cand_f:
                e["name"] = cand_f
                e["selector_type"] = "lay-filter"
                e["runtime_fixed"] = True
            else:
                e["runtime_absent"] = True
            break


def _repair_result_table(elements: list[dict], table_el: dict, dom: dict) -> None:
    """Repair (or revive) the result table element against runtime DOM."""
    best_lay = next((x for x in dom["layIds"] if x["hasTable"]), None)
    plain = None
    for t in dom["tables"]:
        tokens = [x for x in t["cls"].split() if x and x not in _GENERIC_CLASSES]
        if tokens:
            plain = f"table.{tokens[0]} tbody"
            break
    new_name = best_lay["id"] if best_lay else plain
    new_type = "id" if best_lay else "css"
    if not new_name:
        # No candidate at all — mark every table-like element absent.
        for e in elements:
            hay = f"{e.get('name', '')} {e.get('binds', '')}".lower()
            if any(k in hay for k in _TABLE_KEYS):
                e["runtime_absent"] = True
        return
    # Try to revive a previously-absent table element first.
    for e in elements:
        if e.get("runtime_absent") and any(
            k in f"{e.get('name', '')} {e.get('binds', '')}".lower()
            for k in _TABLE_KEYS
        ):
            e.update({"name": new_name, "selector_type": new_type, "runtime_fixed": True})
            e.pop("runtime_absent", None)
            return
    # Otherwise update the matched table element.
    for e in elements:
        if e.get("name") == table_el.get("name") and e.get("page") == table_el.get("page"):
            e.update({"name": new_name, "selector_type": new_type, "runtime_fixed": True})
            break


async def _reload_macros(
    project_id: int, entity_map: dict
) -> dict[str, str]:
    """Re-synthesize macros from the repaired AppMap, upsert in place.

    Returns {macro_name: macro_script_yaml}. Ungrounded read/open macros are
    deactivated (marked pending_review + is_active=False).
    """
    result = macro_factory.synthesize(entity_map)
    produced = {c.name: macro_to_yaml(c) for c in result.candidates}
    from app.core.execution.macro import downgrade_macro, list_macros, update_macro

    async with session_scope() as db:
        existing = await list_macros(
            project_id=project_id, entity=entity_map.get("entity"), db=db
        )
        for m in existing:
            script = produced.get(m.name)
            if script is not None:
                await update_macro(m.id, {"macro_script": script}, db=db)
            elif m.name.startswith(("查看", "打开", "查")):
                if m.is_active:
                    await downgrade_macro(m.id, db=db)
        await db.commit()
    return produced


async def verify_entity(
    *,
    project_id: int,
    entity: str,
    base_url: str | None = None,
    browser=None,
    page=None,
) -> dict:
    """Runtime-verify + repair ONE entity's AppMap elements.

    Visits the entity's list page (from its read/ui macro step-1 URL), dumps
    live DOM, repairs search input / search button / result table, then
    re-synthesizes macros in place.

    Returns stats: {search_fixed, search_absent, button_fixed, button_absent,
    table_fixed, table_absent, deactivated, skipped}.
    """
    stats = {
        "search_fixed": 0, "search_absent": 0,
        "button_fixed": 0, "button_absent": 0,
        "table_fixed": 0, "table_absent": 0,
        "deactivated": 0, "skipped": 0,
    }

    async with session_scope() as db:
        am = (
            await db.execute(
                select(AppMap).where(
                    AppMap.project_id == project_id,
                    AppMap.entity == entity,
                    AppMap.status == "active",
                )
            )
        ).scalars().first()
        if am is None:
            return stats
        entity_map = {
            "entity": am.entity,
            "aliases": am.aliases,
            "routes": am.routes,
            "actions": am.actions,
            "elements": [dict(el) for el in am.elements],
            "db_tables": am.db_tables,
            "extra": am.extra,
            "map_version": am.map_version,
        }

    # List page URL from the AppMap's own read+ui action route (authoritative),
    # NOT from the macro script — the macro URL may itself be wrong (template
    # route drift), which would send verification to a 404 and mis-flag
    # otherwise-present elements as absent.
    url = _resolve_nav_url(_appmap_list_url(entity_map), base_url)
    if not url:
        logger.info("[runtime_verify] %s: 无列表页 URL（缺 read+ui 路由），跳过", entity)
        stats["skipped"] += 1
        return stats

    if page is None:
        if browser is None:
            await db_resource_manager.initialize(create_tables=False, seed_data=False)
            page = await browser_manager.get_page()
        else:
            page = await browser.get_page()

    try:
        await page.goto(url, wait_until="load", timeout=30000)
        await page.wait_for_timeout(1500)
        dom = await page.evaluate(_DUMP_JS)
    except Exception as exc:  # playwright/timeout/OSError all non-fatal per-entity
        logger.warning("[runtime_verify] %s: 页面访问失败 %s", entity, exc)
        stats["skipped"] += 1
        return stats
    if "login" in page.url:
        logger.info("[runtime_verify] %s: 登录态丢失，终止", entity)
        stats["skipped"] += 1
        return stats

    elements = entity_map["elements"]
    from app.core.atlas.source.macro_factory import templates

    # ── search input ───────────────────────────────────────────────
    search_el = templates._find_search_input(entity_map)
    if search_el is not None and not await _present(page, _element_selector(search_el)):
        repaired, absent = _repair_search_input(elements, search_el, dom)
        if repaired:
            stats["search_fixed"] += 1
        else:
            for e in elements:
                if e.get("name") == search_el.get("name"):
                    e["runtime_absent"] = True
            stats["search_absent"] += 1

    # ── search button ──────────────────────────────────────────────
    btn_el = templates._find_search_button(entity_map)
    if btn_el is not None and not await _present(page, _element_selector(btn_el)):
        _repair_search_button(elements, btn_el, dom)
        if any(e.get("name") == btn_el.get("name") and e.get("runtime_fixed")
               for e in elements):
            stats["button_fixed"] += 1
        else:
            stats["button_absent"] += 1

    # ── result table ───────────────────────────────────────────────
    table_el = templates._find_element(entity_map, _TABLE_KEYS)
    if table_el is None:
        # All surveyed table elements absent — try to revive one.
        _repair_result_table(elements, {"name": "", "page": None}, dom)
        if any(e.get("runtime_fixed") for e in elements):
            stats["table_fixed"] += 1
    else:
        probe = _element_selector(table_el)
        if not table_el.get("name") or not await _present(page, probe):
            _repair_result_table(elements, table_el, dom)
            if any(e.get("name") == table_el.get("name") and e.get("runtime_fixed")
                   for e in elements):
                stats["table_fixed"] += 1
            else:
                stats["table_absent"] += 1

    # Persist repaired elements (direct update — repair is not a re-survey,
    # so we must not bump map_version via save_app_map).
    entity_map["elements"] = elements
    async with session_scope() as db:
        am = (
            await db.execute(
                select(AppMap).where(
                    AppMap.project_id == project_id,
                    AppMap.entity == entity,
                    AppMap.status == "active",
                )
            )
        ).scalars().first()
        if am is not None:
            am.elements = elements
            db.add(am)
            await db.commit()

    # Re-synthesize + upsert macros, deactivate ungrounded ones.
    await _reload_macros(project_id, entity_map)

    logger.info(
        "[runtime_verify] %s: %s", entity,
        {k: v for k, v in stats.items() if v},
    )
    return stats


def _macro_list_url(macro: Macro | None, base_url: str | None = None) -> str | None:
    """List-page URL from the macro's step-1 navigate target.

    ``{{base_url}}`` placeholders are substituted with the pipeline base_url
    when provided (template macros emit relative routes gated by the
    placeholder). Returns None when no navigable URL can be derived.
    """
    if macro is None:
        return None
    m = re.search(r"url:\s*(\S+)", macro.macro_script or "")
    if not m or m.group(1) == "null":
        return None
    url = m.group(1).strip("'\"")
    if not url:
        return None
    if "{{base_url}}" in url:
        if not base_url:
            return None
        url = url.replace("{{base_url}}", base_url.rstrip("/"))
    if "{{" in url:
        return None
    return url


def _appmap_list_url(entity_map: dict) -> str | None:
    """List-page URL from the AppMap's read+ui action route (authoritative).

    Prefer the first GET list route among read/ui actions — the canonical page
    a runtime verification should visit. More reliable than the macro script,
    which may carry a drifted template URL.
    """
    from app.core.atlas.source.macro_factory import templates

    for action in entity_map.get("actions", []):
        if action.get("kind") != "read" or action.get("risk_tier") != "ui":
            continue
        route = templates._route_for(entity_map, action.get("name", ""))
        if route and templates._allows_get(route):
            return route.get("url")
    return None


def _resolve_nav_url(url: str | None, base_url: str | None) -> str | None:
    """Make the list-page URL navigable from a relative AppMap route.

    ``base_url`` comes from the pipeline caller. Hash-routed SPA backends
    (e.g. ``shop.html#url=shop/goods/lists``) are handled by appending to the
    entry page when the route path starts with a known ``#url=`` hint; otherwise
    the route is joined to the base as a plain path.
    """
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if not base_url:
        return url
    base = base_url.rstrip("/")
    # Route already carries an explicit hash fragment (…/shop.html#url=…).
    if "#" in url:
        return f"{base}/{url.lstrip('/')}"
    # Hash-routed backend: /goods/lists -> /shop.html#url=goods/lists
    if url.startswith("/"):
        return f"{base}/shop.html#url={url.lstrip('/')}"
    return f"{base}/{url.lstrip('/')}"


async def verify_project(
    *, project_id: int, entity: str | None = None, base_url: str | None = None
) -> dict:
    """Runtime-verify all (or one) active AppMaps of a project.

    Returns {entity: stats}.
    """
    async with session_scope() as db:
        stmt = select(AppMap).where(
            AppMap.project_id == project_id,
            AppMap.status == "active",
        )
        if entity:
            stmt = stmt.where(AppMap.entity == entity)
        maps = (await db.execute(stmt)).scalars().all()
        entities = [m.entity for m in maps]

    if not entities:
        logger.info("[runtime_verify] project %s: 无活跃 AppMap", project_id)
        return {}

    page = None
    try:
        await db_resource_manager.initialize(create_tables=False, seed_data=False)
        page = await browser_manager.get_page()
    except Exception:
        page = None

    if page is None:
        logger.error("[runtime_verify] project %s: 浏览器不可用", project_id)
        return {}

    out: dict[str, dict] = {}
    try:
        for ent in entities:
            out[ent] = await verify_entity(
                project_id=project_id, entity=ent, base_url=base_url, page=page
            )
    finally:
        try:
            await browser_manager.close()
        except Exception:
            pass
    return out


async def run(*, project_id: int, entity: str | None = None, base_url: str | None = None) -> dict:
    """Pipeline entry: runtime-verify + repair for a project (or one entity)."""
    return await verify_project(project_id=project_id, entity=entity, base_url=base_url)
