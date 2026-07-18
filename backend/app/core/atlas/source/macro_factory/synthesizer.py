"""Macro synthesizer: pick templates, instantiate, run the two deterministic checks.

Produces MacroCandidate objects — nothing is persisted here. Two checks only:
  1. grounding: every url/selector resolves to an AppMap entry (enforced inside
     templates by returning None; re-verified here against the produced steps)
  2. structural: steps parse as MacroScript and contain at least one step
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.core.atlas.source.macro_factory import templates
from app.core.atlas.source.macro_factory.templates import MacroCandidate

logger = logging.getLogger(__name__)


@dataclass
class SynthesisResult:
    candidates: list[MacroCandidate] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)


def pick_templates(action: dict) -> list:
    """Templates to instantiate for an action (usually one).

    Money writes get two: the write macro itself and a sibling field-read
    macro ('查{query}商品价格') so multi-intent chains have a pure numeric
    `value` key for resolver expressions.
    """
    kind = action.get("kind")
    risk = action.get("risk_tier")
    if kind == "read" and risk == "ui":
        return [templates.list_view, templates.list_open]
    if kind == "read" and risk == "data":
        return [templates.crud_read]
    if kind == "write" and risk == "money":
        return [templates.crud_write, templates.crud_field_read]
    if kind == "write" and risk == "data":
        return [templates.crud_write, templates.basic_navigate]
    if kind == "write" and risk == "ui":
        return [templates.basic_navigate]
    return []


def pick_template(action: dict):
    tmpls = pick_templates(action)
    return tmpls[0] if tmpls else None


def synthesize(entity_map: dict) -> SynthesisResult:
    result = SynthesisResult()
    entity = entity_map.get("entity", "?")
    seen_names: set[str] = set()

    for action in entity_map.get("actions", []):
        tmpls = pick_templates(action)
        if not tmpls:
            result.gaps.append(
                f"{entity}.{action.get('name')}: kind/risk 不符任何模板（留给飞轮）"
            )
            continue
        produced = False
        for tmpl in tmpls:
            candidate = tmpl(entity_map, action)
            if candidate is None:
                continue
            problems = _check_candidate(candidate, entity_map)
            if problems:
                result.validation_errors.extend(problems)
                continue
            if candidate.name in seen_names:
                # Two actions sharing the same set_fields[0] produce identical
                # names — suffix the source action to keep both addressable.
                candidate.name = f"{candidate.name}（{candidate.source_action}）"
            seen_names.add(candidate.name)
            result.candidates.append(candidate)
            produced = True
        if not produced:
            result.gaps.append(
                f"{entity}.{action.get('name')}: 槽位无法接地（缺路由/元素）"
            )

    return result


def _check_candidate(candidate: MacroCandidate, entity_map: dict) -> list[str]:
    problems: list[str] = []

    if not candidate.macro_script:
        return [f"{candidate.name}: macro_script 为空"]

    known_paths = {
        templates._norm_path(r.get("url", "")) for r in entity_map.get("routes", [])
    }
    # page_url overrides (GET-rendered page for JSON-only endpoints) are
    # equally valid stage-2 navigation targets.
    known_paths |= {
        templates._norm_path(r["page_url"])
        for r in entity_map.get("routes", [])
        if r.get("page_url")
    }
    known_selectors: set[str] = set()
    for el in entity_map.get("elements", []):
        known_selectors.add(el.get("name"))
        known_selectors.add(templates._selector(el))
        if el.get("selector_type") == "id":
            # layui scopes rendered tables by lay-id=<table id>
            known_selectors.add(f"[lay-id='{el['name']}']")

    def _selector_grounded(sel: str) -> bool:
        if sel in known_selectors:
            return True
        # Composed selectors (e.g. row-scoped "[lay-id='t'] tr [data-x-id]")
        # are grounded when they embed at least one known element selector.
        return any(k and k in sel for k in known_selectors)

    for step in candidate.macro_script:
        url = (
            step.get("payload", {}).get("url")
            if isinstance(step.get("payload"), dict)
            else None
        )
        if url:
            # Strip the base ({{base_url}} placeholder or scheme+host) and the
            # query string; the remaining path must resolve to a route entry.
            path = url.replace("{{base_url}}", "")
            path = re.sub(r"^https?://[^/]+", "", path).split("?")[0]
            if path and path not in known_paths:
                problems.append(f"{candidate.name}: url '{path}' 不在 AppMap routes 中")
        selector = step.get("target_selector")
        if selector and not _selector_grounded(selector):
            problems.append(
                f"{candidate.name}: selector '{selector}' 不在 AppMap elements 中"
            )

    from app.core.execution.macro.schemas import MacroScript

    try:
        MacroScript(steps=candidate.macro_script)
    except (ValueError, TypeError, KeyError) as exc:
        problems.append(f"{candidate.name}: macro_script 结构非法: {exc}")

    return problems
