"""AppMap output validation: schema check + source spot-check (anti-hallucination).

Both layers are deterministic, no LLM. Returns a list of problems; empty means
pass. write_app_map refuses to persist when problems are non-empty.
"""

from __future__ import annotations

import logging
import os

from app.core.atlas.source.schemas import (
    ACTION_KINDS,
    RISK_TIERS,
    SELECTOR_TYPES,
    AppMapPayload,
)

logger = logging.getLogger(__name__)

_LINE_WINDOW = 10


def validate_app_map(
    payload: AppMapPayload, project_path: str | None = None
) -> list[str]:
    problems: list[str] = []
    problems.extend(_validate_schema(payload))
    if project_path:
        problems.extend(_spot_check_source(payload, project_path))
    return problems


def _validate_schema(payload: AppMapPayload) -> list[str]:
    problems: list[str] = []
    table_names = {t.table for t in payload.db_tables}

    for r in payload.routes:
        if not r.url:
            problems.append(f"route '{r.name}' 缺少 url")
        elif not (r.url.startswith("/") or r.url.startswith(("http://", "https://"))):
            problems.append(
                f"route '{r.name}' url '{r.url}' 须以 '/' 开头（站点相对路径）"
            )

    for el in payload.elements:
        if el.selector_type is not None and el.selector_type not in SELECTOR_TYPES:
            problems.append(
                f"element '{el.name}' selector_type='{el.selector_type}' 非法"
                f"（须 ∈ {SELECTOR_TYPES}）"
            )

    for a in payload.actions:
        if a.kind not in ACTION_KINDS:
            problems.append(
                f"action '{a.name}' kind='{a.kind}' 非法（须 ∈ {ACTION_KINDS}）"
            )
        if a.risk_tier not in RISK_TIERS:
            problems.append(
                f"action '{a.name}' risk_tier='{a.risk_tier}' 非法（须 ∈ {RISK_TIERS}）"
            )
        for t in a.touches_tables:
            if t not in table_names:
                problems.append(f"action '{a.name}' 引用的表 '{t}' 不在 db_tables 中")

    if not payload.actions:
        problems.append("actions 为空：调研未产出任何动作")
    return problems


def _spot_check_source(payload: AppMapPayload, project_path: str) -> list[str]:
    """Re-read source files at claimed locations and verify symbols exist."""
    problems: list[str] = []

    for a in payload.actions:
        if not a.controller or a.line is None:
            problems.append(
                f"action '{a.name}' 缺少 controller/line 溯源（回源抽检必填）"
            )
            continue
        if not _symbol_at_location(project_path, a.controller, a.line, a.name):
            problems.append(
                f"action '{a.name}' 在 {a.controller}:{a.line} 附近未找到（疑似幻觉条目）"
            )

    for el in payload.elements:
        if not el.page or el.line is None:
            continue
        if not _symbol_at_location(project_path, el.page, el.line, el.name):
            problems.append(
                f"element '{el.name}' 在 {el.page}:{el.line} 附近未找到（疑似幻觉条目）"
            )
    return problems


def _symbol_at_location(
    project_path: str, rel_file: str, line: int, symbol: str
) -> bool:
    abs_path = _resolve_file(project_path, rel_file)
    if abs_path is None:
        return False
    try:
        with open(abs_path, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return False
    lo = max(0, line - 1 - _LINE_WINDOW)
    hi = min(len(lines), line + _LINE_WINDOW)
    window = "".join(lines[lo:hi])
    return symbol in window


_SKIP_DIRS = {"node_modules", "vendor", ".git", "__pycache__", "dist", "build"}


def _resolve_file(project_path: str, rel_file: str) -> str | None:
    direct = os.path.join(project_path, rel_file)
    if os.path.isfile(direct):
        return direct
    basename = os.path.basename(rel_file)
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        if basename in files:
            return os.path.join(root, basename)
    return None
