"""Template library: AppMap x template instantiation -> macro candidates.

Pure Python, no LLM. Every step target (url / selector / field) MUST resolve to
a concrete AppMap entry (grounding rule). When any slot cannot be filled the
template returns None -> the action is dropped and recorded as a coverage gap;
nothing is ever fabricated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_BINDS_SUFFIX_RE = re.compile(r"(输入框|搜索框|下拉框|选择器|文本框|表格|按钮|字段)$")


def _entity_cn(entity_map: dict) -> str:
    """Chinese business name of the entity (first CJK alias), else identifier."""
    for alias in entity_map.get("aliases") or []:
        if isinstance(alias, str) and _CJK_RE.search(alias):
            return alias
    return entity_map["entity"]


def _field_label(element: dict | None, fallback: str) -> str:
    """Chinese label for a field, derived from the matched element's binds."""
    if element:
        binds = (element.get("binds") or "").strip()
        for token in reversed(binds.split()):
            token = _BINDS_SUFFIX_RE.sub("", token)
            if token and _CJK_RE.search(token):
                return token
        cleaned = _BINDS_SUFFIX_RE.sub("", binds)
        if cleaned and _CJK_RE.search(cleaned):
            return cleaned
    return fallback


def _readable_subject(entity_cn: str, field_cn: str) -> str:
    """entity+field display name, dropping redundant overlap (商品+商品名称→商品名称)."""
    if field_cn and entity_cn and field_cn.startswith(entity_cn):
        return field_cn
    return f"{entity_cn}{field_cn}"


@dataclass
class MacroCandidate:
    name: str
    description: str
    trigger_patterns: list[str]
    parameters: list[dict]
    macro_script: list[dict]
    risk_tier: str
    requires_confirmation: bool
    source_action: str
    app_map_version: int


def _route_for(entity_map: dict, action_name: str) -> dict | None:
    for r in entity_map.get("routes", []):
        if r.get("source_action") == action_name:
            return r
    return None


def _allows_get(route: dict) -> bool:
    """Browser navigate issues GET; POST-only routes cannot back a page macro."""
    return "GET" in (route.get("method") or "GET").upper()


def _norm_path(url: str) -> str:
    """Site-relative path with a leading slash (scheme/host stripped if present)."""
    u = (url or "").strip()
    u = re.sub(r"^https?://[^/]+", "", u)
    return u if u.startswith("/") else f"/{u}"


def _full_url(entity_map: dict, route: dict) -> str:
    """Navigable URL: extra.base_url + route path; {{base_url}} placeholder when
    the survey could not discover the site origin."""
    base = ((entity_map.get("extra") or {}).get("base_url") or "").rstrip("/")
    return f"{base or '{{base_url}}'}{_norm_path(route['url'])}"


def _needs_base_url(entity_map: dict) -> bool:
    return not ((entity_map.get("extra") or {}).get("base_url") or "").strip()


_BASE_URL_PARAM = {
    "name": "base_url",
    "type": "string",
    "required": False,
    "description": "后台站点根地址（如 http://localhost:8080），宏执行时必填",
}


def _with_base_url(entity_map: dict, parameters: list[dict]) -> list[dict]:
    if _needs_base_url(entity_map):
        return [*parameters, dict(_BASE_URL_PARAM)]
    return parameters


_SELECTOR_BUILDERS = {
    "id": lambda n: f"#{n}",
    "name": lambda n: f"[name='{n}']",
    "class": lambda n: f".{n}",
    "lay-filter": lambda n: f"[lay-filter='{n}']",
    "css": lambda n: n,
    "text": lambda n: f"text={n}",
    # name carries the full attribute (e.g. "data-goods-id") -> [data-goods-id]
    "data-attr": lambda n: f"[{n}]",
}


def _selector(element: dict) -> str:
    """Playwright-resolvable selector for an AppMap element.

    With selector_type the symbol is unambiguous; without it, fall back to a
    CSS union covering the two most common attribute forms (id / name).
    """
    name = element["name"]
    builder = _SELECTOR_BUILDERS.get(element.get("selector_type") or "")
    return builder(name) if builder else f"#{name}, [name='{name}']"


def _find_element(entity_map: dict, keywords: tuple[str, ...]) -> dict | None:
    for el in entity_map.get("elements", []):
        if el.get("runtime_absent"):
            # Runtime re-survey proved this element does not exist on the
            # live page (survey over-claimed from source templates).
            continue
        hay = f"{el.get('name', '')} {el.get('binds', '')}".lower()
        if any(k.lower() in hay for k in keywords):
            return el
    return None


# Field names that are form toggles / display switches, never the value being
# written. `crud_write` must not pick these as the input to fill (e.g. an
# action with set_fields=[..., "price", ...] must match the price box, not the
# "is_unify_price" switch).
_WRITE_FIELD_EXCLUDE = (
    "is_", "_show", "_switch", "_enable", "_open", "if_", "allow_",
)


def _find_write_input(entity_map: dict, fields: list[str]) -> dict | None:
    """Best-effort match of a writable input field from an action's set_fields.

    Prefers an exact element name match; falls back to substring search but
    skips boolean toggles / display switches so money/data writes target the
    real input (price box, stock box), not an is_* sibling.
    """
    candidates = entity_map.get("elements", [])
    for field in fields:
        for el in candidates:
            if el.get("runtime_absent"):
                continue
            if el.get("name") == field and not _is_toggle_field(el):
                return el
    for field in fields:
        for el in candidates:
            if el.get("runtime_absent"):
                continue
            hay = f"{el.get('name', '')} {el.get('binds', '')}".lower()
            if field.lower() in hay and not _is_toggle_field(el):
                return el
    return None


def _is_toggle_field(el: dict) -> bool:
    name = (el.get("name") or "").lower()
    return any(name.startswith(prefix) for prefix in _WRITE_FIELD_EXCLUDE)


def _find_search_input(entity_map: dict) -> dict | None:
    """Search text box: binds marks it as an input, not a button."""
    for el in entity_map.get("elements", []):
        if el.get("runtime_absent"):
            continue
        binds = el.get("binds", "")
        hay = f"{el.get('name', '')} {binds}".lower()
        if "按钮" in binds or "button" in hay:
            continue
        if any(k in binds for k in ("搜索框", "输入框", "筛选")) or any(
            k in hay for k in ("search", "keyword", "query")
        ):
            return el
    return None


def _find_search_button(entity_map: dict) -> dict | None:
    """Search submit button (layui forms submit via click, not Enter)."""
    for el in entity_map.get("elements", []):
        binds = el.get("binds", "")
        hay = f"{el.get('name', '')} {binds}".lower()
        if not any(k in binds for k in ("按钮", "提交")) and "button" not in hay:
            continue
        if any(k in hay for k in ("搜索", "search", "筛选", "查询")):
            return el
    return None


def _find_save_button(entity_map: dict) -> dict | None:
    """Form save button on the edit page.

    A generic keyword scan matches the LIST search button first (its binds
    say 搜索提交按钮), so: prefer binds explicitly saying 保存, then fall
    back to save/submit symbols with search buttons excluded.
    """
    for el in entity_map.get("elements", []):
        if "保存" in el.get("binds", ""):
            return el
    for el in entity_map.get("elements", []):
        binds = el.get("binds", "")
        hay = f"{el.get('name', '')} {binds}".lower()
        if "搜索" in binds or "search" in hay:
            continue
        if any(k in hay for k in ("save", "submit", "确定")) or "提交" in binds:
            return el
    return None


def _tab_click_step(input_el: dict, entity_map: dict, step_number: int) -> dict | None:
    """Click step that reveals the tab containing input_el, when the survey
    marked the element with `tab` (layui renders inactive .layui-tab-item
    panels display:none — input actions wait for visibility and would time
    out; get_attribute reads hidden values fine, so reads skip this).

    The tab itself must be a surveyed text-type element whose name equals
    the marker; otherwise the tab click would be fabricated (grounding).
    """
    tab_name = input_el.get("tab")
    if not tab_name:
        return None
    for el in entity_map.get("elements", []):
        if el.get("selector_type") == "text" and el.get("name") == tab_name:
            return {
                "step_number": step_number,
                "type": "action",
                "event_type": "click",
                "source": "dom",
                "target_selector": _selector(el),
                "payload": {},
            }
    return None


def _candidate(
    entity_map: dict,
    action: dict,
    name: str,
    steps: list[dict],
    trigger_patterns: list[str],
    parameters: list[dict],
    requires_confirmation: bool = False,
    risk_tier: str | None = None,
    description: str | None = None,
) -> MacroCandidate:
    return MacroCandidate(
        name=name,
        description=description if description is not None else action.get("business_rule", ""),
        trigger_patterns=trigger_patterns,
        parameters=parameters,
        macro_script=steps,
        risk_tier=risk_tier or action["risk_tier"],
        requires_confirmation=requires_confirmation,
        source_action=action["name"],
        app_map_version=entity_map.get("map_version", 1),
    )


def basic_navigate(entity_map: dict, action: dict) -> MacroCandidate | None:
    """Fallback write/ui template: navigate to the entity's list page or the
    action's own URL.  Does not attempt to fill fields or click save —
    intended for actions where set_fields / save_button are unavailable.
    """
    route = _route_for(entity_map, action["name"])
    if not route:
        return None
    if not _allows_get(route):
        # POST-only action — try the entity's list page instead
        for a in entity_map.get("actions", []):
            if a.get("kind") == "read":
                r = _route_for(entity_map, a["name"])
                if r and _allows_get(r):
                    route = r
                    break
        if not _allows_get(route):
            return None

    entity_cn = _entity_cn(entity_map)
    steps = [
        {
            "step_number": 1,
            "type": "action",
            "event_type": "navigate",
            "source": "dom",
            "payload": {"url": _full_url(entity_map, route)},
        },
        {
            "step_number": 2,
            "type": "action",
            "event_type": "wait",
            "source": "dom",
            "payload": {"seconds": 1},
        },
    ]
    return _candidate(
        entity_map,
        action,
        name=f"打开{entity_cn}" if entity_cn != entity_map["entity"] else f"打开{entity_cn}页面",
        steps=steps,
        trigger_patterns=[f"打开{entity_cn}列表", f"查看{entity_cn}"],
        parameters=[],
        requires_confirmation=False,
        description=f"导航到{entity_cn}页面",
    )


def list_view(entity_map: dict, action: dict) -> MacroCandidate | None:
    """UI read macro: open list URL -> search -> extract result table."""
    route = _route_for(entity_map, action["name"])
    if route is None or not _allows_get(route):
        return None
    search = _find_search_input(entity_map)
    result = _find_element(
        entity_map, ("表格", "列表", "table", "结果", "清单", "list")
    )
    if search is None or result is None:
        return None
    button = _find_search_button(entity_map)

    steps: list[dict] = [
        {
            "step_number": 1,
            "type": "action",
            "event_type": "navigate",
            "source": "dom",
            "payload": {"url": _full_url(entity_map, route)},
        },
        {
            "step_number": 2,
            "type": "action",
            "event_type": "wait",
            "source": "dom",
            "payload": {"seconds": 1},
        },
        {
            "step_number": 3,
            "type": "action",
            "event_type": "input",
            "source": "dom",
            "target_selector": _selector(search),
            # Enter submits only when there is no distinct search button;
            # otherwise the click below submits and Enter must NOT fire twice.
            "payload": {
                "text": "{{query}}",
                "clear_first": True,
                "enter": button is None,
            },
        },
    ]
    if button is not None:
        steps.append(
            {
                "step_number": 4,
                "type": "action",
                "event_type": "click",
                "source": "dom",
                "target_selector": _selector(button),
                "payload": {},
            }
        )
    # The table reloads via AJAX after the search; extracting immediately
    # would capture the stale pre-search rows.
    steps.append(
        {
            "step_number": len(steps) + 1,
            "type": "action",
            "event_type": "wait",
            "source": "dom",
            "payload": {"seconds": 1},
        }
    )
    steps.append(
        {
            "step_number": len(steps) + 1,
            "type": "extract",
            "event_type": "get_text",
            "source": "dom",
            "target_selector": _rows_container(result),
            "extract_type": "get_text",
            "key": "rows",
            # attached: an empty/hidden rows container reads "" honestly
            # instead of timing out on visibility.
            "payload": {"state": "attached"},
        }
    )
    entity_cn = _entity_cn(entity_map)
    return _candidate(
        entity_map,
        action,
        name=f"查看{{query}}{entity_cn}",
        steps=steps,
        trigger_patterns=[
            f"查看{{{{query}}}}{entity_cn}",
            "找{{query}}",
            f"定位{{{{query}}}}{entity_cn}",
        ],
        parameters=_with_base_url(
            entity_map,
            [
                {
                    "name": "query",
                    "type": "string",
                    "required": True,
                    "description": f"{entity_cn}名/编号",
                }
            ],
        ),
    )


def list_open(entity_map: dict, action: dict) -> MacroCandidate | None:
    """Navigation macro: open the list page and extract visible rows (no search).

    Sibling of list_view for bare '打开X列表' utterances — no query parameter,
    no input/click steps, so the router has a deterministic answer to
    navigation-only intents instead of failing on a missing query.
    """
    route = _route_for(entity_map, action["name"])
    if route is None or not _allows_get(route):
        return None
    result = _find_element(
        entity_map, ("表格", "列表", "table", "结果", "清单", "list")
    )
    if result is None:
        return None

    steps: list[dict] = [
        {
            "step_number": 1,
            "type": "action",
            "event_type": "navigate",
            "source": "dom",
            "payload": {"url": _full_url(entity_map, route)},
        },
        {
            "step_number": 2,
            "type": "action",
            "event_type": "wait",
            "source": "dom",
            "payload": {"seconds": 1},
        },
        {
            "step_number": 3,
            "type": "extract",
            "event_type": "get_text",
            "source": "dom",
            "target_selector": _rows_container(result),
            "extract_type": "get_text",
            "key": "rows",
            # attached: an empty/hidden rows container reads "" honestly
            # instead of timing out on visibility.
            "payload": {"state": "attached"},
        },
    ]
    entity_cn = _entity_cn(entity_map)
    return _candidate(
        entity_map,
        action,
        name=f"打开{entity_cn}列表",
        steps=steps,
        trigger_patterns=[
            f"打开{entity_cn}列表",
            f"进入{entity_cn}列表",
            f"显示{entity_cn}列表",
        ],
        parameters=_with_base_url(entity_map, []),
        description=f"打开{entity_cn}列表页并提取当前展示的{entity_cn}（不需要搜索词）",
    )


def crud_read(entity_map: dict, action: dict) -> MacroCandidate | None:
    """Data read macro: open the action's page -> extract the target field."""
    route = _route_for(entity_map, action["name"])
    fields = action.get("set_fields") or []
    target = _find_element(entity_map, tuple(fields)) if fields else None
    if route is None or target is None or not _allows_get(route):
        return None

    steps = [
        {
            "step_number": 1,
            "type": "action",
            "event_type": "navigate",
            "source": "dom",
            "payload": {"url": _full_url(entity_map, route)},
        },
        {
            "step_number": 2,
            "type": "action",
            "event_type": "wait",
            "source": "dom",
            "payload": {"seconds": 1},
        },
        {
            "step_number": 3,
            "type": "extract",
            "event_type": "get_text",
            "source": "dom",
            "target_selector": _selector(target),
            "extract_type": "get_text",
            "key": "value",
            "payload": {},
        },
    ]
    field = fields[0] if fields else "值"
    entity_cn = _entity_cn(entity_map)
    subject = _readable_subject(entity_cn, _field_label(target, field))
    return _candidate(
        entity_map,
        action,
        name=f"查{{query}}{subject}",
        steps=steps,
        trigger_patterns=[
            f"查{{{{query}}}}{subject}",
            f"{{{{query}}}}的{subject}是多少",
        ],
        parameters=_with_base_url(
            entity_map,
            [
                {
                    "name": "query",
                    "type": "string",
                    "required": True,
                    "description": f"{entity_cn}名/编号",
                }
            ],
        ),
    )


def _list_surface(entity_map: dict) -> tuple[dict, dict, dict | None, dict] | None:
    """(list_route, search_input, search_button, result_table) of the entity's
    read/ui list page, or None when any grounding slot is missing."""
    list_route = None
    for action in entity_map.get("actions", []):
        if action.get("kind") == "read" and action.get("risk_tier") == "ui":
            r = _route_for(entity_map, action["name"])
            if r and _allows_get(r):
                list_route = r
                break
    search = _find_search_input(entity_map)
    result = _find_element(
        entity_map, ("表格", "列表", "table", "结果", "清单", "list")
    )
    if list_route is None or search is None or result is None:
        return None
    return list_route, search, _find_search_button(entity_map), result


def _entity_pk(entity_map: dict) -> str | None:
    """Primary key of the entity's own table (goods -> goods_id)."""
    entity = entity_map.get("entity", "")
    for t in entity_map.get("db_tables", []):
        if t.get("table") == entity and t.get("pk"):
            return t["pk"]
    return None


def _stage2_url(entity_map: dict, route: dict) -> str:
    """Stage-2 (edit page) URL with the resolved entity id.

    route["url"] is the action's API endpoint; the GET-rendered page can
    differ (JSON-only save endpoints, SPA shells) — an optional `page_url`
    route field overrides it. The id query key is framework-specific
    (`?goods_id=` here, not `?id=`): an optional `id_param` route field
    overrides the default "id".
    """
    page = dict(route)
    page["url"] = route.get("page_url") or route["url"]
    id_param = route.get("id_param") or "id"
    return f"{_full_url(entity_map, page)}?{id_param}={{{{entity_id}}}}"


def _rows_container(result: dict) -> str:
    """Selector covering the result rows of a list page.

    css selectors are surveyor-exact and used verbatim (server-rendered
    tables, JS-partial containers, ...). id selectors follow the layui
    convention: the source <table> is hidden and rows render into a sibling
    view container, so the bare id would extract "".
    """
    if result.get("selector_type") == "css":
        return _selector(result)
    if result.get("selector_type") == "id":
        return f"[lay-id='{result['name']}'] .layui-table-body"
    return _selector(result)


def _first_row_id_selector(result: dict, row_id_el: dict) -> str:
    """Selector of the first result row's id carrier.

    A css row-id element is surveyor-exact and already row-addressed (e.g.
    "table.x tr[data-order-id]") — used verbatim. layui id tables scope the
    data-attr carrier under the rendered view container's first row.
    """
    if row_id_el.get("selector_type") == "css":
        return _selector(row_id_el)
    if result.get("selector_type") == "id":
        return (
            f"[lay-id='{result['name']}'] .layui-table-body "
            f"tr[data-index='0'] {_selector(row_id_el)}"
        )
    return f"{_selector(result)} {_selector(row_id_el)}"


def _find_row_id_element(entity_map: dict) -> dict | None:
    """Row id carrier (data-attr element), preferring data-<pk-with-dashes>."""
    data_els = [
        el
        for el in entity_map.get("elements", [])
        if el.get("selector_type") == "data-attr"
    ]
    if not data_els:
        return None
    pk = _entity_pk(entity_map)
    if pk:
        want = f"data-{pk.replace('_', '-')}"
        for el in data_els:
            if el.get("name") == want:
                return el
    return data_els[0]


def _search_steps(
    entity_map: dict, route: dict, search: dict, button: dict | None
) -> list[dict]:
    """Shared stage-1: open list page -> keyword search."""
    steps: list[dict] = [
        {
            "step_number": 1,
            "type": "action",
            "event_type": "navigate",
            "source": "dom",
            "payload": {"url": _full_url(entity_map, route)},
        },
        {
            "step_number": 2,
            "type": "action",
            "event_type": "wait",
            "source": "dom",
            "payload": {"seconds": 1},
        },
        {
            "step_number": 3,
            "type": "action",
            "event_type": "input",
            "source": "dom",
            "target_selector": _selector(search),
            "payload": {
                "text": "{{query}}",
                "clear_first": True,
                "enter": button is None,
            },
        },
    ]
    if button is not None:
        steps.append(
            {
                "step_number": 4,
                "type": "action",
                "event_type": "click",
                "source": "dom",
                "target_selector": _selector(button),
                "payload": {},
            }
        )
    return steps


def crud_write(entity_map: dict, action: dict) -> MacroCandidate | None:
    """Money write macro, two-stage: search the row by name -> extract its id
    from the row's data-attr -> open edit page -> fill absolute value -> save.

    Requires the engine's extracted_data -> params feedback ({{entity_id}} in
    stage 2). Always carries requires_confirmation=True (money gate). Parameters
    accept absolute values only — relative expressions ("降5毛") must be resolved
    by the caller before invocation.
    """
    route = _route_for(entity_map, action["name"])
    fields = action.get("set_fields") or []
    input_el = _find_write_input(entity_map, fields) if fields else None
    save_el = _find_save_button(entity_map)
    if route is None or input_el is None or save_el is None:
        return None
    if not _allows_get(route):
        return None
    surface = _list_surface(entity_map)
    row_id_el = _find_row_id_element(entity_map)
    if surface is None or row_id_el is None:
        return None
    list_route, search, button, result = surface

    entity_cn = _entity_cn(entity_map)
    field = fields[0] if fields else "value"
    subject = _readable_subject(entity_cn, _field_label(input_el, field))

    steps = _search_steps(entity_map, list_route, search, button)
    steps += [
        {
            "step_number": 5,
            "type": "action",
            "event_type": "wait",
            "source": "dom",
            "payload": {"seconds": 1},
        },
        {
            "step_number": 6,
            "type": "extract",
            "event_type": "get_attribute",
            "source": "dom",
            "target_selector": _first_row_id_selector(result, row_id_el),
            "extract_type": "get_attribute",
            "key": "entity_id",
            "payload": {"attribute": row_id_el["name"]},
        },
        {
            "step_number": 7,
            "type": "action",
            "event_type": "navigate",
            "source": "dom",
            "payload": {"url": _stage2_url(entity_map, route)},
        },
        {
            "step_number": 8,
            "type": "action",
            "event_type": "wait",
            "source": "dom",
            "payload": {"seconds": 1},
        },
    ]
    tab_step = _tab_click_step(input_el, entity_map, 9)
    if input_el.get("tab") and tab_step is None:
        # Field lives in a tab the survey did not capture — clicking it
        # would be fabrication; drop the candidate (honest gap).
        return None
    if tab_step is not None:
        steps.append(tab_step)
    steps += [
        {
            "step_number": 9 if tab_step is None else 10,
            "type": "action",
            "event_type": "input",
            "source": "dom",
            "target_selector": _selector(input_el),
            # Save is a separate click below; Enter must not submit early.
            "payload": {"text": "{{new_value}}", "clear_first": True, "enter": False},
        },
        {
            "step_number": 10 if tab_step is None else 11,
            "type": "action",
            "event_type": "click",
            "source": "dom",
            "target_selector": _selector(save_el),
            "payload": {},
        },
    ]
    return _candidate(
        entity_map,
        action,
        name=f"改{{query}}{subject}",
        steps=steps,
        trigger_patterns=[
            f"改{{{{query}}}}{subject}为{{{{new_value}}}}",
            f"把{{{{query}}}}的{subject}改成{{{{new_value}}}}",
        ],
        parameters=_with_base_url(
            entity_map,
            [
                {
                    "name": "query",
                    "type": "string",
                    "required": True,
                    "description": f"{entity_cn}名/编号（搜索关键词）",
                },
                {
                    "name": "new_value",
                    "type": "number",
                    "required": True,
                    "description": "绝对值，禁止相对表达式",
                },
            ],
        ),
        requires_confirmation=True,
        description=f"修改{entity_cn}的{subject}",
    )


def crud_field_read(entity_map: dict, action: dict) -> MacroCandidate | None:
    """Field read macro ('查{query}商品价格'): stage-1 search -> first row's
    id -> edit page -> read the field input's current value as `value`.

    Shares crud_write's grounding minus the save button; steps never write,
    so the candidate is risk 'ui' even though it derives from a money action.
    Gives multi-intent chains a pure numeric `value` key that resolver
    expressions ({{1.value}} * 0.9) can actually consume.
    """
    route = _route_for(entity_map, action["name"])
    fields = action.get("set_fields") or []
    input_el = _find_element(entity_map, tuple(fields)) if fields else None
    if route is None or input_el is None:
        return None
    if not _allows_get(route):
        return None
    surface = _list_surface(entity_map)
    row_id_el = _find_row_id_element(entity_map)
    if surface is None or row_id_el is None:
        return None
    list_route, search, button, result = surface

    entity_cn = _entity_cn(entity_map)
    field = fields[0] if fields else "value"
    subject = _readable_subject(entity_cn, _field_label(input_el, field))

    steps = _search_steps(entity_map, list_route, search, button)
    steps += [
        {
            "step_number": 5,
            "type": "action",
            "event_type": "wait",
            "source": "dom",
            "payload": {"seconds": 1},
        },
        {
            "step_number": 6,
            "type": "extract",
            "event_type": "get_attribute",
            "source": "dom",
            "target_selector": _first_row_id_selector(result, row_id_el),
            "extract_type": "get_attribute",
            "key": "entity_id",
            "payload": {"attribute": row_id_el["name"]},
        },
        {
            "step_number": 7,
            "type": "action",
            "event_type": "navigate",
            "source": "dom",
            "payload": {"url": _stage2_url(entity_map, route)},
        },
        {
            "step_number": 8,
            "type": "action",
            "event_type": "wait",
            "source": "dom",
            "payload": {"seconds": 1},
        },
        {
            "step_number": 9,
            "type": "extract",
            "event_type": "get_attribute",
            "source": "dom",
            "target_selector": _selector(input_el),
            "extract_type": "get_attribute",
            "key": "value",
            "payload": {"attribute": "value"},
        },
    ]
    return _candidate(
        entity_map,
        action,
        name=f"查{{query}}{subject}",
        steps=steps,
        trigger_patterns=[
            f"查{{{{query}}}}{subject}",
            f"{{{{query}}}}的{subject}是多少",
        ],
        parameters=_with_base_url(
            entity_map,
            [
                {
                    "name": "query",
                    "type": "string",
                    "required": True,
                    "description": f"{entity_cn}名/编号（搜索关键词）",
                }
            ],
        ),
        risk_tier="ui",
        description=f"查询{entity_cn}的{subject}",
    )


# ─────────────────────────────────────────────────────────────────────
# Row-action templates (list-page inline operations) — v3.1
#
# 商城列表页的运营操作（上架/下架/删除等）是"行内 lay-event 按钮"，
# 不离开列表页。CSS 无法表达"含某文本的行里的按钮"，故用 run_js 定位
# 目标行并触发按钮（等价于真实运营操作）。edit_stock 额外打开"修改库存"
# 弹窗填 sku 值后提交。
# ─────────────────────────────────────────────────────────────────────

# JS: 在 layui 表格中定位含 {{query}} 文本的行，点击指定 lay-event 按钮。
# 返回 true/false 供宏判定。query 由宏参数注入（已 JSON 安全化）。
def _row_click_script(lay_event: str, table_selector: str) -> str:
    """Build a run_js body that clicks the row button for the searched goods.

    {{query}} is injected at macro runtime as a parameter. The script polls
    briefly for the row (hash-routed list pages render async), then finds the
    button with the given lay-event and clicks it. ``table_selector`` is
    data-driven from the AppMap (result table element).
    """
    return (
        "() => {\n"
        "  const q = ('{{query}}' || '').toLowerCase();\n"
        "  return new Promise((resolve) => {\n"
        "    let attempts = 0;\n"
        "    const poll = () => {\n"
        f"      const table = document.querySelector({table_selector!r}) "
        "|| document.querySelector('.layui-table-main') || document.querySelector('table');\n"
        "      if (table) {\n"
        "        const rows = table.querySelectorAll('tbody tr, .layui-table-body tr');\n"
        "        for (const tr of rows) {\n"
        "          const txt = (tr.textContent || '').toLowerCase();\n"
        "          if (q && !txt.includes(q)) continue;\n"
        f"          const btn = tr.querySelector('[lay-event={lay_event}]');\n"
        "          if (btn) { btn.click(); return resolve(true); }\n"
        "        }\n"
        "      }\n"
        "      if (++attempts > 20) return resolve(false);\n"
        "      setTimeout(poll, 250);\n"
        "    };\n"
        "    poll();\n"
        "  });\n"
        "}"
    )


def _confirm_click_script() -> str:
    """Click the layui confirm dialog's primary button (确定/是)."""
    return (
        "() => {\n"
        "  const btns = document.querySelectorAll('.layui-layer-btn0, "
        ".layui-layer-btn1, .layui-layer-btn a');\n"
        "  for (const b of btns) {\n"
        "    const t = (b.textContent || '').trim();\n"
        "    if (t.includes('确定') || t.includes('确认') || t === '是') { "
        "b.click(); return true; }\n"
        "  }\n"
        "  return false;\n"
        "}"
    )


def _switch_tab_script(tab_name: str, tab_selector: str) -> str:
    """Click the row-state tab (销售中/仓库中/预警中/全部) by label.

    ``tab_selector`` is data-driven from the AppMap (row_tab_scope).
    """
    return (
        "() => {\n"
        f"  const tabs = document.querySelectorAll({tab_selector!r});\n"
        "  for (const li of tabs) {\n"
        f"    const t = (li.textContent || '').trim();\n"
        f"    if (t === {tab_name!r} || t.includes({tab_name!r})) "
        "{ li.click(); return true; }\n"
        "  }\n"
        "  return false;\n"
        "}"
    )


def _open_stock_dialog_script(table_selector: str, lay_event: str = "editStock") -> str:
    """Open the row edit dialog for the searched row.

    Polls briefly for the table row to appear (hash-routed list pages render
    async) so the click is not attempted before rows exist. ``table_selector``
    and the row button ``lay_event`` are data-driven from the AppMap.
    """
    return (
        "() => {\n"
        "  const q = ('{{query}}' || '').toLowerCase();\n"
        "  return new Promise((resolve) => {\n"
        "    let attempts = 0;\n"
        "    const poll = () => {\n"
        f"      const table = document.querySelector({table_selector!r}) "
        "|| document.querySelector('.layui-table-main') || document.querySelector('table');\n"
        "      if (table) {\n"
        "        const rows = table.querySelectorAll('tbody tr, .layui-table-body tr');\n"
        "        for (const tr of rows) {\n"
        "          const txt = (tr.textContent || '').toLowerCase();\n"
        "          if (q && !txt.includes(q)) continue;\n"
        f"          const btn = tr.querySelector('[lay-event={lay_event}]');\n"
        "          if (btn) { btn.click(); return resolve(true); }\n"
        "        }\n"
        "      }\n"
        "      if (++attempts > 20) return resolve(false);\n"
        "      setTimeout(poll, 250);\n"
        "    };\n"
        "    poll();\n"
        "  });\n"
        "}"
    )


def _fill_stock_dialog_script(fields: list[tuple[str, str]]) -> str:
    """Fill the row edit dialog inputs and submit.

    ``fields`` is a list of (input_name, macro_param_name) — the dialog input's
    ``name`` and the macro parameter that supplies its value. Field names and
    params are data-driven from the AppMap row_dialog config. Submits via the
    lay-submit button (triggers the dialog's layui form submit), not the
    dialog's close button.
    """
    set_lines = []
    for input_name, param_name in fields:
        set_lines.append(
            f"  set({input_name!r}, {{{{{param_name}}}}});"
        )
    set_body = "\n".join(set_lines)
    return (
        "() => {\n"
        "  const layer = document.querySelector('.layui-layer');\n"
        "  if (!layer) return false;\n"
        "  const set = (name, val) => {\n"
        "    const inp = [...layer.querySelectorAll('input, textarea')].find(i => i.name === name);\n"
        "    if (inp && val !== undefined && val !== null && val !== '') {\n"
        "      inp.value = val; inp.dispatchEvent(new Event('input', {bubbles:true}));\n"
        "      inp.dispatchEvent(new Event('change', {bubbles:true}));\n"
        "    }\n"
        "  };\n"
        + set_body
        + "\n"
        "  const submit = layer.querySelector('[lay-submit]');\n"
        "  if (submit) { submit.click(); return true; }\n"
        "  return false;\n"
        "}"
    )


def _row_list_surface(entity_map: dict) -> dict | None:
    """List-page route for row operations (route only — no element grounding).

    Row buttons are dynamic (not in the survey), so only the read/ui GET list
    route is needed. Prefers an explicit ``extra.row_list_route``, then a GET
    route whose source_action/url looks like the entity's main list page
    (``<entity>List`` / ``<entity>list`` / ``lists``), else the first read/ui
    GET route. Returns the route dict or None.
    """
    explicit = ((entity_map.get("extra") or {}).get("row_list_route"))
    if explicit:
        for r in entity_map.get("routes", []):
            if r.get("url") == explicit or r.get("name") == explicit:
                return r
    entity = str(entity_map.get("entity", "")).lower()
    entity_lists = {f"{entity}list", f"{entity}_list", f"{entity}lists"}
    candidates = []
    for action in entity_map.get("actions", []):
        if action.get("kind") != "read" or action.get("risk_tier") != "ui":
            continue
        r = _route_for(entity_map, action.get("name", ""))
        if not r or not _allows_get(r):
            continue
        name = str(action.get("name", "")).lower()
        # Entity-scoped list page first: memberList / member_list / memberlists
        if name in entity_lists:
            return r
        if name.endswith(("list", "lists")) or name == "index":
            candidates.append(r)
    if candidates:
        return candidates[0]
    # Bare 'lists' action (entity/ lists) — common fallback.
    for action in entity_map.get("actions", []):
        if action.get("kind") != "read" or action.get("risk_tier") != "ui":
            continue
        if str(action.get("name", "")).lower() == "lists":
            r = _route_for(entity_map, action.get("name", ""))
            if r and _allows_get(r):
                return r
    return None


def _row_list_url(entity_map: dict, route: dict) -> str:
    """Navigable list-page URL for row operations.

    Hash-routed backends get the entry-page form with the module prefix
    (default ``shop/``, overridable via ``extra.hash_prefix``) so the row
    operations land on the real list page; otherwise the plain route URL is
    used. base_url stays a {{base_url}} placeholder for engine substitution.
    """
    path = route.get("url", "").lstrip("/")
    if path and not path.startswith("http"):
        prefix = ((entity_map.get("extra") or {}).get("hash_prefix") or "shop/")
        return f"{{{{base_url}}}}/shop.html#url={prefix}{path}"
    return _full_url(entity_map, route)


def _row_table_selector(entity_map: dict) -> str:
    """Result-table selector for row operations, data-driven from AppMap.

    Preference:
      1. ``extra.row_table`` explicit override.
      2. AppMap element whose id matches ``<entity>_list`` (the canonical
         list-page table id — goods_list, member_list, order_list…).
      3. First AppMap id-typed list/table element.
      4. Fallback to common layui table ids.
    """
    cfg = (entity_map.get("extra") or {}).get("row_table")
    if cfg:
        return cfg
    entity = str(entity_map.get("entity", "")).lower()
    for el in entity_map.get("elements", []):
        if el.get("runtime_absent") or el.get("selector_type") != "id":
            continue
        if el.get("name") == f"{entity}_list":
            return f"[lay-id='{el['name']}']"
    table_el = _find_element(
        entity_map, ("表格", "列表", "table", "结果", "清单", "list")
    )
    if table_el and table_el.get("selector_type") == "id":
        return f"[lay-id='{table_el['name']}']"
    return "[lay-id=goods_list], .layui-table-main, table"


def _row_tab_selector(entity_map: dict) -> str:
    """Row-state tab selector (销售中/仓库中/预警中/全部), data-driven.

    Falls back to the goods list tab convention.
    """
    tab_scope = ((entity_map.get("extra") or {}).get("row_tab_scope") or "goods_list_tab")
    return f"[lay-filter='{tab_scope}'] li, .layui-tab-title li"


def _row_dialog_fields(entity_map: dict, action: dict) -> list[tuple[str, str]]:
    """Dialog input fields for a row-dialog operation.

    Data-driven via ``extra.row_dialogs`` — a dict keyed by action name:
        {"adjustBalance": {"fields": [["adjust_num", "value"], ...]}}
    Falls back to the stock-dialog convention for editGoodsStock/editStock
    (price/stock → new_value/new_stock).
    """
    cfg = (entity_map.get("extra") or {}).get("row_dialogs") or {}
    action_name = action.get("name", "")
    if action_name in cfg:
        raw = cfg[action_name].get("fields") or []
        return [(str(f[0]), str(f[1])) for f in raw if isinstance(f, (list, tuple)) and len(f) == 2]
    name = action_name.lower()
    if "stock" in name:
        return [("price", "new_value"), ("stock", "new_stock")]
    if "balance" in name or "point" in name or "integral" in name or "growth" in name:
        return [("adjust_num", "new_value")]
    if "price" in name:
        return [("price", "new_value")]
    return [("price", "new_value")]


def _row_dialog_lay_event(entity_map: dict, action: dict) -> str:
    """Row button lay-event that opens the dialog.

    Prefers ``extra.row_dialogs.<action>.lay_event``; falls back to the
    snake_case of the action name (modifyBalance -> modify_balance), then the
    stock convention (editStock).
    """
    cfg = (entity_map.get("extra") or {}).get("row_dialogs") or {}
    action_name = action.get("name", "")
    if action_name in cfg and cfg[action_name].get("lay_event"):
        return cfg[action_name]["lay_event"]
    name = action_name.lower()
    if "balance" in name:
        return "adjust_balance"
    if "point" in name or "integral" in name:
        return "adjust_integral"
    if "growth" in name:
        return "adjust_growth"
    if "stock" in name:
        return "editStock"
    import re as _re
    snake = _re.sub(r"(?<!^)(?=[A-Z])", "_", action_name).lower()
    return snake


def _field_verb(entity_map: dict, action: dict, fields: list[tuple[str, str]]) -> str:
    """Chinese verb for a row-dialog operation (改价/改库存/改余额/改积分…).

    Prefers ``extra.row_dialogs.<action>.verb``; falls back to a name-based
    guess from the action/field names.
    """
    cfg = (entity_map.get("extra") or {}).get("row_dialogs") or {}
    action_name = action.get("name", "")
    if action_name in cfg and cfg[action_name].get("verb"):
        return cfg[action_name]["verb"]
    name = action_name.lower()
    if "balance" in name:
        return "余额"
    if "point" in name or "integral" in name:
        return "积分"
    if "growth" in name:
        return "成长值"
    if "stock" in name:
        return "库存"
    if "price" in name:
        return "价"
    if fields:
        return fields[0][0]
    return "值"


def _row_lay_event(entity_map: dict, action_name: str) -> str | None:
    """Row lay-event for an action, data-driven via extra.row_actions.

    ``extra.row_actions`` maps action_name → lay-event (e.g.
    {"onGoods": "on_goods", "offGoods": "off_goods"}); falls back to the
    built-in convention table; delete*/del → delete/del; otherwise snake_case
    of the action name.
    """
    cfg = (entity_map.get("extra") or {}).get("row_actions") or {}
    if action_name in cfg:
        return cfg[action_name]
    if action_name in _ROW_ACTION_LAY_EVENTS:
        return _ROW_ACTION_LAY_EVENTS[action_name]
    lower = action_name.lower()
    if lower.startswith("delete") or lower == "del":
        return "delete" if lower != "del" else "del"
    if lower == "off":
        return "off"
    if lower == "on":
        return "on"
    import re as _re
    return _re.sub(r"(?<!^)(?=[A-Z])", "_", action_name).lower()


def row_action(entity_map: dict, action: dict) -> MacroCandidate | None:
    """List-row inline operation (上架/下架/删除等): navigate list -> click the
    target row's lay-event button -> confirm dialog.

    Does NOT require AppMap element grounding for the row button (rows are
    dynamic). The action name (e.g. 'onGoods'/'offGoods') maps to the row
    lay-event via a small convention table; unknown actions fall back to the
    snake_case action name.
    """
    route = _row_list_surface(entity_map)
    if route is None:
        return None
    # lay-event: data-driven via extra.row_actions, else convention table.
    lay_event = _row_lay_event(entity_map, action.get("name", ""))
    if lay_event is None:
        return None

    entity_cn = _entity_cn(entity_map)
    verb = _row_action_verb(action.get("name", ""))
    table_selector = _row_table_selector(entity_map)
    tab_selector = _row_tab_selector(entity_map)
    # Row state tab: 上架 operates on 仓库中 (下架) rows; 下架/删除 on 销售中.
    tab = "仓库中" if lay_event in ("on_goods",) else "销售中"
    steps = [
        {
            "step_number": 1,
            "type": "action",
            "event_type": "navigate",
            "source": "dom",
            "payload": {"url": _row_list_url(entity_map, route)},
        },
        {"step_number": 2, "type": "action", "event_type": "wait", "source": "dom",
         "payload": {"seconds": 1}},
        {"step_number": 3, "type": "action", "event_type": "run_js", "source": "dom",
         "payload": {"script": _switch_tab_script(tab, tab_selector), "continue_on_error": True}},
        {"step_number": 4, "type": "action", "event_type": "run_js", "source": "dom",
         "payload": {"script": _row_click_script(lay_event, table_selector)}},
        {"step_number": 5, "type": "action", "event_type": "wait", "source": "dom",
         "payload": {"seconds": 1}},
        {"step_number": 6, "type": "action", "event_type": "run_js", "source": "dom",
         "payload": {"script": _confirm_click_script(), "continue_on_error": True}},
    ]
    return _candidate(
        entity_map,
        action,
        name=f"{verb}{{query}}{entity_cn}",
        steps=steps,
        trigger_patterns=[
            f"{verb}{{{{{{query}}}}}}{entity_cn}",
            f"把{{{{{{query}}}}}}{entity_cn}{verb}",
        ],
        parameters=_with_base_url(
            entity_map,
            [
                {
                    "name": "query",
                    "type": "string",
                    "required": True,
                    "description": f"{entity_cn}名/编号",
                }
            ],
        ),
        requires_confirmation=False,
        description=f"{verb}{entity_cn}（列表行内操作）",
    )


def edit_stock(entity_map: dict, action: dict) -> MacroCandidate | None:
    """List-row stock/price edit: navigate list -> open 修改库存 dialog ->
    fill price/stock -> submit.

    Covers 改价 + 编辑库存 (money/data writes on the row's stock dialog).
    Requires a query (goods name) and new absolute values.
    """
    route = _row_list_surface(entity_map)
    if route is None:
        return None
    entity_cn = _entity_cn(entity_map)

    params = [{"name": "query", "type": "string", "required": True,
               "description": f"{entity_cn}名/编号"}]
    table_selector = _row_table_selector(entity_map)
    fields = _row_dialog_fields(entity_map, action)
    lay_event = _row_dialog_lay_event(entity_map, action)
    steps = [
        {"step_number": 1, "type": "action", "event_type": "navigate", "source": "dom",
         "payload": {"url": _row_list_url(entity_map, route)}},
        {"step_number": 2, "type": "action", "event_type": "wait", "source": "dom",
         "payload": {"seconds": 1}},
        {"step_number": 3, "type": "action", "event_type": "run_js", "source": "dom",
         "payload": {"script": _open_stock_dialog_script(table_selector, lay_event)}},
        {"step_number": 4, "type": "action", "event_type": "wait", "source": "dom",
         "payload": {"seconds": 1}},
    ]
    fill_js = _fill_stock_dialog_script(fields)
    # verb + params from fields
    verb = "改" + _field_verb(entity_map, action, fields)
    for input_name, param_name in fields:
        required = "price" not in input_name or len(fields) == 1
        params.append({
            "name": param_name,
            "type": "number",
            "required": required,
            "description": f"{entity_cn} {input_name}（绝对值）",
        })

    steps.append({"step_number": 5, "type": "action", "event_type": "run_js",
                  "source": "dom", "payload": {"script": fill_js}})
    steps.append({"step_number": 6, "type": "action", "event_type": "wait",
                  "source": "dom", "payload": {"seconds": 1}})
    return _candidate(
        entity_map,
        action,
        name=f"{verb}{{query}}{entity_cn}",
        steps=steps,
        trigger_patterns=[
            f"{verb}{{{{{{query}}}}}}{entity_cn}",
            f"把{{{{{{query}}}}}}{entity_cn}{verb}",
        ],
        parameters=_with_base_url(entity_map, params),
        requires_confirmation=False,
        description=f"{verb}{entity_cn}（列表行内弹窗操作）",
    )


_ROW_ACTION_VERBS = {
    "onGoods": "上架",
    "offGoods": "下架",
    "deleteGoods": "删除",
    "on_goods": "上架",
    "off_goods": "下架",
    "delete": "删除",
}


def _row_action_verb(action_name: str) -> str:
    """Chinese verb for a row action (上架/下架/删除…)."""
    if action_name in _ROW_ACTION_VERBS:
        return _ROW_ACTION_VERBS[action_name]
    lower = action_name.lower()
    if lower.startswith("delete") or lower in ("del",):
        return "删除"
    if lower in ("off", "off_goods", "offgoods"):
        return "下架"
    if lower in ("on", "on_goods", "ongoods"):
        return "上架"
    return "操作"

_ROW_ACTION_LAY_EVENTS = {
    "onGoods": "on_goods",
    "offGoods": "off_goods",
    "on_goods": "on_goods",
    "off_goods": "off_goods",
    "deleteGoods": "delete",
    "delete": "delete",
}


# ─────────────────────────────────────────────────────────────────────
# Detail-action template — list → detail page → perform action (售后处理).
#
# Covers after-sales / approval flows that live on a DETAIL page rather than
# the list row: refund agree/refuse/close, withdrawal approval, etc.
# Flow: list → locate target row's 详情 link → open detail → click action
# (onclick event) → dialog confirm (optionally fill a reason first).
# ─────────────────────────────────────────────────────────────────────


def _detail_list_url(entity_map: dict, route: dict) -> str:
    """List-page URL for detail-action flows (hash-routed, module prefix)."""
    path = route.get("url", "").lstrip("/")
    if path and not path.startswith("http"):
        prefix = ((entity_map.get("extra") or {}).get("hash_prefix") or "shop/")
        return f"{{{{base_url}}}}/shop.html#url={prefix}{path}"
    return _full_url(entity_map, route)


def _detail_open_link_script(table_selector: str) -> str:
    """Find the target row's 详情 link and return its detail URL.

    Polls for the row (async list render), reads the href of the 详情 link
    (which encodes the detail id, e.g. order_goods_id), then navigates.
    ``query_param`` names the detail id param in the link.
    """
    return (
        "() => {\n"
        "  const q = ('{{query}}' || '').toLowerCase();\n"
        "  return new Promise((resolve) => {\n"
        "    let attempts = 0;\n"
        "    const poll = () => {\n"
        f"      const table = document.querySelector({table_selector!r}) "
        "|| document.querySelector('.layui-table-main') || document.querySelector('table');\n"
        "      if (table) {\n"
        "        const rows = table.querySelectorAll('tbody tr, .layui-table-body tr');\n"
        "        for (const tr of rows) {\n"
        "          const txt = (tr.textContent || '').toLowerCase();\n"
        "          if (q && !txt.includes(q)) continue;\n"
        "          const link = [...tr.querySelectorAll('a')].find(a => "
        "(a.textContent||'').includes('详情') || (a.textContent||'').includes('Detail'));\n"
        "          if (link) { resolve(link.getAttribute('href') || ''); return; }\n"
        "        }\n"
        "      }\n"
        "      if (++attempts > 20) return resolve('');\n"
        "      setTimeout(poll, 250);\n"
        "    };\n"
        "    poll();\n"
        "  });\n"
        "}"
    )


def _detail_click_action_script(event_name: str) -> str:
    """Click the detail-page action button whose onclick contains event_name.

    e.g. orderRefundAgree / orderRefundRefuse / orderRefundClose.
    """
    return (
        "() => {\n"
        "  const btns = document.querySelectorAll('[onclick]');\n"
        "  for (const b of btns) {\n"
        f"    const o = b.getAttribute('onclick') || '';\n"
        f"    if (o.includes({event_name!r})) {{ b.click(); return true; }}\n"
        "  }\n"
        "  return false;\n"
        "}"
    )


def _detail_dialog_confirm_script(reason_field: str | None = None) -> str:
    """Confirm the detail action dialog; optionally fill a reason first.

    ``reason_field`` names the dialog's reason textarea (e.g.
    refund_refuse_reason) to fill with {{reason}} before confirming.
    """
    fill = ""
    if reason_field:
        fill = (
            f"  const ta = layer.querySelector('textarea[name={reason_field!r}]');\n"
            "  if (ta) { ta.value = ('{{reason}}' || ''); "
            "ta.dispatchEvent(new Event('input',{bubbles:true})); }\n"
        )
    return (
        "() => {\n"
        "  const layer = document.querySelector('.layui-layer');\n"
        "  if (!layer) return false;\n"
        + fill
        + "  const btn = layer.querySelector('.layui-layer-btn0');\n"
        "  if (btn) { btn.click(); return true; }\n"
        "  return false;\n"
        "}"
    )


def detail_action(entity_map: dict, action: dict) -> MacroCandidate | None:
    """List → detail → action flow (售后处理/审批).

    Navigates the entity's list page, finds the target row's 详情 link, opens
    the detail page, clicks the action button (agree/refuse/close…), and
    confirms the dialog (filling a reason for refuse-type actions).

    Config via ``extra.detail_actions``:
        {"orderRefundRefuse": {"event": "orderRefundRefuse",
                               "reason_field": "refund_refuse_reason"}}
    Falls back to snake_case of the action name as the onclick event.
    """
    route = _row_list_surface(entity_map)
    if route is None:
        return None
    entity_cn = _entity_cn(entity_map)
    cfg = (entity_map.get("extra") or {}).get("detail_actions") or {}
    action_name = action.get("name", "")
    acfg = cfg.get(action_name) or {}
    event_name = acfg.get("event") or _detail_event_name(action_name)
    reason_field = acfg.get("reason_field")
    verb = acfg.get("verb") or _detail_action_verb(action_name)

    table_selector = _row_table_selector(entity_map)
    steps = [
        {"step_number": 1, "type": "action", "event_type": "navigate", "source": "dom",
         "payload": {"url": _detail_list_url(entity_map, route)}},
        {"step_number": 2, "type": "action", "event_type": "wait", "source": "dom",
         "payload": {"seconds": 1}},
        # Extract detail URL from the target row's 详情 link into {{detail_url}}
        {"step_number": 3, "type": "extract", "extract_type": "run_js", "source": "dom",
         "key": "detail_url",
         "payload": {"script": _detail_open_link_script(table_selector)}},
        # Navigate to the detail URL
        {"step_number": 4, "type": "action", "event_type": "navigate", "source": "dom",
         "payload": {"url": "{{detail_url}}"}},
        {"step_number": 5, "type": "action", "event_type": "wait", "source": "dom",
         "payload": {"seconds": 1}},
        # Click the action button
        {"step_number": 6, "type": "action", "event_type": "run_js", "source": "dom",
         "payload": {"script": _detail_click_action_script(event_name)}},
        {"step_number": 7, "type": "action", "event_type": "wait", "source": "dom",
         "payload": {"seconds": 1}},
        # Confirm dialog (+ optional reason)
        {"step_number": 8, "type": "action", "event_type": "run_js", "source": "dom",
         "payload": {"script": _detail_dialog_confirm_script(reason_field), "continue_on_error": True}},
    ]
    params = [{"name": "query", "type": "string", "required": True,
               "description": f"{entity_cn}名/编号/订单号"}]
    if reason_field:
        params.append({"name": "reason", "type": "string", "required": True,
                       "description": f"{verb}理由"})
    return _candidate(
        entity_map,
        action,
        name=f"{verb}{{query}}{entity_cn}",
        steps=steps,
        trigger_patterns=[
            f"{verb}{{{{{{query}}}}}}{entity_cn}",
            f"把{{{{{{query}}}}}}{entity_cn}{verb}",
        ],
        parameters=_with_base_url(entity_map, params),
        requires_confirmation=False,
        description=f"{verb}{entity_cn}（详情页操作）",
    )


def _detail_event_name(action_name: str) -> str:
    """onclick event name for a detail action: orderRefundAgree etc.

    Prefers a convention mapping; falls back to snake_case.
    """
    lower = action_name.lower()
    if lower == "agree":
        return "orderRefundAgree"
    if lower == "refuse":
        return "orderRefundRefuse"
    if lower == "close":
        return "orderRefundClose"
    if lower == "receive":
        return "orderRefundReceive"
    if lower == "complete":
        return "orderRefundComplete"
    if lower == "activerefund":
        return "orderRefundActive"
    return action_name


def _detail_action_verb(action_name: str) -> str:
    lower = action_name.lower()
    if lower == "agree":
        return "同意退款"
    if lower == "refuse":
        return "拒绝退款"
    if lower == "close":
        return "关闭维权"
    if lower == "receive":
        return "收货"
    if lower == "complete":
        return "完成退款"
    if lower == "activerefund":
        return "主动退款"
    return "处理"
