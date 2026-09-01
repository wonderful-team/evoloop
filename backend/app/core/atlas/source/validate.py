"""AppMap output validation: schema check + source spot-check + graph reachability.

All checks are deterministic and LLM-free. Returns a list of problems; empty means
pass. write_app_map refuses to persist when problems are non-empty.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import or_, select

from app.core.atlas.constants import ACTION_KINDS, RISK_TIERS, SELECTOR_TYPES
from app.core.atlas.source.schemas import AppMapPayload
from app.core.file import FileStatus, read_file
from app.infrastructure.database import session_scope
from app.models import CodeEntity, CodeRelation, Repository, SourceFile
from app.utils.http import is_http_url

logger = logging.getLogger(__name__)

_LINE_WINDOW = 10
_MAX_GRAPH_DEPTH = 5
_GRAPH_CONFIDENCE = ("EXTRACTED", "INFERRED")


async def validate_app_map(
    payload: AppMapPayload,
    project_path: str | None = None,
    project_id: int | None = None,
) -> list[str]:
    """Validate an AppMap payload.

    Args:
        payload: AppMap payload to validate.
        project_path: Optional local project path for source spot-checks.
        project_id: Optional project ID for CodeRelation graph reachability checks.

    Returns:
        List of validation problems; empty means pass.
    """
    problems: list[str] = []
    problems.extend(_validate_schema(payload))
    if project_path:
        problems.extend(_spot_check_source(payload, project_path))
    if project_id:
        problems.extend(await _validate_graph_reachability(payload, project_id))
    return problems


def _validate_schema(payload: AppMapPayload) -> list[str]:
    problems: list[str] = []
    table_names = {t.table for t in payload.db_tables}

    for r in payload.routes:
        if not r.url:
            problems.append(f"route '{r.name}' 缺少 url")
        elif not (r.url.startswith("/") or is_http_url(r.url)):
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

    start_line = max(1, line - _LINE_WINDOW)
    end_line = line + _LINE_WINDOW
    result = read_file(abs_path, start_line=start_line, end_line=end_line)
    if result.status != FileStatus.SUCCESS:
        return False

    return symbol in result.content


def _resolve_file(project_path: str, rel_file: str) -> str | None:
    direct = os.path.join(project_path, rel_file)
    if os.path.isfile(direct):
        return direct
    basename = os.path.basename(rel_file)
    from app.core.file import FileTraverser

    for full_path in FileTraverser.walk(project_path):
        if os.path.basename(full_path) == basename:
            return full_path
    return None


async def _validate_graph_reachability(
    payload: AppMapPayload, project_id: int
) -> list[str]:
    """Verify each action can reach its claimed DB tables via CodeRelation."""
    problems: list[str] = []
    async with session_scope() as session:
        for action in payload.actions:
            if not action.controller or not action.touches_tables:
                continue
            controller_path = action.controller.replace("\\", "/")
            start_ids = await _resolve_entity_ids(
                session, project_id, action.name, path=controller_path
            )
            if not start_ids:
                continue
            for table in action.touches_tables:
                target_ids = await _resolve_entity_ids(session, project_id, table)
                if not target_ids:
                    continue
                reachable = await _is_reachable_in_graph(session, start_ids, target_ids)
                if not reachable:
                    problems.append(
                        f"Action '{action.name}' → table '{table}': "
                        f"no reachable path found in CodeRelation graph "
                        f"(confidence: {', '.join(_GRAPH_CONFIDENCE)}). "
                        f"Possible hallucination or missing extraction."
                    )
    return problems


async def _resolve_entity_ids(
    session, project_id: int, name: str, *, path: str | None = None
) -> set[int]:
    """Find CodeEntity IDs matching a symbol name, optionally within a file path."""
    stmt = (
        select(CodeEntity.id)
        .join(SourceFile)
        .join(Repository)
        .where(Repository.project_id == project_id)
    )
    if path is not None:
        stmt = stmt.where(SourceFile.path == path)
    stmt = stmt.where(_entity_name_matches(CodeEntity, name))
    result = await session.execute(stmt)
    return {row[0] for row in result.all()}


def _entity_name_matches(entity_cls, name: str):
    """SQL filter: entity.name or full_name matches the given symbol."""
    return or_(
        entity_cls.name == name,
        entity_cls.full_name == name,
        entity_cls.full_name.endswith(f".{name}"),
    )


async def _is_reachable_in_graph(
    session, start_ids: set[int], target_ids: set[int]
) -> bool:
    """Breadth-first search in CodeRelation up to _MAX_GRAPH_DEPTH."""
    if not start_ids or not target_ids:
        return False
    if start_ids & target_ids:
        return True

    visited = set(start_ids)
    frontier = set(start_ids)
    depth = 0

    while frontier and depth < _MAX_GRAPH_DEPTH:
        stmt = select(CodeRelation.target_entity_id).where(
            CodeRelation.source_entity_id.in_(frontier),
            CodeRelation.target_entity_id.is_not(None),
            CodeRelation.confidence.in_(_GRAPH_CONFIDENCE),
        )
        result = await session.execute(stmt)
        next_ids: set[int] = set()
        for row in result.all():
            tid = row[0]
            if tid is None:
                continue
            if tid in target_ids:
                return True
            next_ids.add(tid)

        frontier = next_ids - visited
        visited.update(next_ids)
        depth += 1

    return False
