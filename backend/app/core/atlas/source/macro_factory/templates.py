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
    input_el = _find_element(entity_map, tuple(fields)) if fields else None
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
