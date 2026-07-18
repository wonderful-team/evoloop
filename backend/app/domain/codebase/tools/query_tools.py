"""Index-query tools consumed by generation Agents.

All tools resolve the external ``project_id`` to the local active ``Repository``
and then query the SQL-backed codebase index. Results are returned as lists of
dicts to keep the interface language-agnostic.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.core.context.manager import ContextManager
from app.core.monitoring.ui_actions import require_project_for_tool
from app.core.tools import evoloop_tool
from app.infrastructure.database import session_scope
from app.models import (
    CodeChunk,
    CodeEntity,
    CodeRelation,
    Repository,
    SecurityFinding,
    SourceFile,
)

logger = logging.getLogger(__name__)


async def _resolve_repo_id(project_id: int | None) -> int | None:
    """Resolve project_id to the active local repository ID."""
    pid = ContextManager.resolve_project_id(
        explicit_id=project_id, allow_global=False, request_temp=True
    )
    if pid == 0:
        result = await require_project_for_tool(
            tool_name="query_code_chunks",
            tool_category="codebase_query",
            prompt="Please select a project to query the codebase index:",
        )
        if isinstance(result, str):
            return None
        pid = result

    if project_id is not None:
        pid = project_id

    async with session_scope() as session:
        stmt = (
            select(Repository.id)
            .where(Repository.project_id == pid)
            .where(Repository.sync_status.notin_(["IGNORED", "DISCONNECTED"]))
            .limit(1)
        )
        result = await session.execute(stmt)
        repo_id = result.scalar_one_or_none()
        return repo_id


def _chunk_to_dict(chunk: CodeChunk) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "source_file_id": chunk.source_file_id,
        "chunk_type": chunk.chunk_type,
        "identifier": chunk.identifier,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "is_api_route": chunk.is_api_route,
        "api_method": chunk.api_method,
        "api_path": chunk.api_path,
        "is_db_model": chunk.is_db_model,
        "db_table_name": chunk.db_table_name,
    }


def _relation_to_dict(rel: CodeRelation) -> dict[str, Any]:
    return {
        "id": rel.id,
        "source_entity_id": rel.source_entity_id,
        "target_entity_id": rel.target_entity_id,
        "target_name": rel.target_name,
        "relation_type": rel.relation_type,
        "confidence": rel.confidence,
    }


def _source_file_to_dict(sf: SourceFile) -> dict[str, Any]:
    return {
        "id": sf.id,
        "repository_id": sf.repository_id,
        "path": sf.path,
        "checksum": sf.checksum,
        "scan_status": sf.scan_status,
        "security_scan_status": sf.security_scan_status,
        "parsed_at": sf.parsed_at.isoformat() if sf.parsed_at else None,
        "last_indexed_at": sf.last_indexed_at.isoformat() if sf.last_indexed_at else None,
    }


def _security_finding_to_dict(finding: SecurityFinding) -> dict[str, Any]:
    return {
        "id": finding.id,
        "source_file_id": finding.source_file_id,
        "finding_type": finding.finding_type,
        "severity": finding.severity,
        "description": finding.description,
        "line_start": finding.line_start,
        "line_end": finding.line_end,
        "code_snippet": finding.code_snippet,
    }


@evoloop_tool(summary_template="evoloop.tool_summary.query_code_chunks")
async def query_code_chunks(
    project_id: int | None = None,
    type: str | None = None,
    file_path: str | None = None,
    is_api_route: bool | None = None,
    is_db_model: bool | None = None,
    search: str | None = None,
    limit: int = 100,
) -> str:
    """Query CodeChunk rows for the current project.

    Args:
        project_id: Optional project ID. Auto-detected from context if omitted.
        type: Filter by chunk_type (e.g. "function", "class", "module").
        file_path: Filter by source file path (substring match).
        is_api_route: Filter by API route flag.
        is_db_model: Filter by DB model flag.
        search: Substring search on identifier or content.
        limit: Maximum number of rows to return.

    Returns:
        Formatted list of matching CodeChunk records.
    """
    repo_id = await _resolve_repo_id(project_id)
    if repo_id is None:
        return "No active repository found for this project."

    async with session_scope() as session:
        stmt = select(CodeChunk).join(SourceFile, CodeChunk.source_file_id == SourceFile.id)
        stmt = stmt.where(SourceFile.repository_id == repo_id)
        if type:
            stmt = stmt.where(CodeChunk.chunk_type == type)
        if file_path:
            stmt = stmt.where(SourceFile.path.contains(file_path))
        if is_api_route is not None:
            stmt = stmt.where(CodeChunk.is_api_route == is_api_route)
        if is_db_model is not None:
            stmt = stmt.where(CodeChunk.is_db_model == is_db_model)
        if search:
            stmt = stmt.where(
                (CodeChunk.identifier.contains(search))
                | (CodeChunk.content.contains(search))
            )
        stmt = stmt.order_by(CodeChunk.id).limit(limit)
        result = await session.execute(stmt)
        chunks = result.scalars().all()

    if not chunks:
        return "No matching code chunks found.", {"count": 0}

    payload = [_chunk_to_dict(c) for c in chunks]
    return _format_json_list(payload), {"count": len(payload)}


@evoloop_tool(summary_template="evoloop.tool_summary.query_code_relations")
async def query_code_relations(
    project_id: int | None = None,
    source_entity_id: int | None = None,
    target_entity_id: int | None = None,
    relation_type: str | None = None,
    confidence: str | None = None,
    limit: int = 100,
) -> str:
    """Query CodeRelation rows for the current project.

    Args:
        project_id: Optional project ID. Auto-detected from context if omitted.
        source_entity_id: Filter by source entity ID.
        target_entity_id: Filter by resolved target entity ID.
        relation_type: Filter by relation type (calls, inherits, imports, defines).
        confidence: Filter by confidence (EXTRACTED, INFERRED, AMBIGUOUS).
        limit: Maximum number of rows to return.

    Returns:
        Formatted list of matching CodeRelation records.
    """
    repo_id = await _resolve_repo_id(project_id)
    if repo_id is None:
        return "No active repository found for this project."

    async with session_scope() as session:
        stmt = (
            select(CodeRelation)
            .join(CodeEntity, CodeRelation.source_entity_id == CodeEntity.id)
            .join(SourceFile, CodeEntity.file_id == SourceFile.id)
        )
        stmt = stmt.where(SourceFile.repository_id == repo_id)
        if source_entity_id is not None:
            stmt = stmt.where(CodeRelation.source_entity_id == source_entity_id)
        if target_entity_id is not None:
            stmt = stmt.where(CodeRelation.target_entity_id == target_entity_id)
        if relation_type:
            stmt = stmt.where(CodeRelation.relation_type == relation_type)
        if confidence:
            stmt = stmt.where(CodeRelation.confidence == confidence)
        stmt = stmt.order_by(CodeRelation.id).limit(limit)
        result = await session.execute(stmt)
        relations = result.scalars().all()

    if not relations:
        return "No matching code relations found.", {"count": 0}

    payload = [_relation_to_dict(r) for r in relations]
    return _format_json_list(payload), {"count": len(payload)}


@evoloop_tool(summary_template="evoloop.tool_summary.query_source_files")
async def query_source_files(
    project_id: int | None = None,
    path_pattern: str | None = None,
    scan_status: str | None = None,
    ext: str | None = None,
    limit: int = 100,
) -> str:
    """Query SourceFile rows for the current project.

    Args:
        project_id: Optional project ID. Auto-detected from context if omitted.
        path_pattern: Substring match on the relative path.
        scan_status: Filter by scan_status (pending, completed, failed).
        ext: File extension filter (e.g. ".py").
        limit: Maximum number of rows to return.

    Returns:
        Formatted list of matching SourceFile records.
    """
    repo_id = await _resolve_repo_id(project_id)
    if repo_id is None:
        return "No active repository found for this project."

    async with session_scope() as session:
        stmt = select(SourceFile).where(SourceFile.repository_id == repo_id)
        if path_pattern:
            stmt = stmt.where(SourceFile.path.contains(path_pattern))
        if scan_status:
            stmt = stmt.where(SourceFile.scan_status == scan_status)
        if ext:
            stmt = stmt.where(SourceFile.path.endswith(ext))
        stmt = stmt.order_by(SourceFile.id).limit(limit)
        result = await session.execute(stmt)
        files = result.scalars().all()

    if not files:
        return "No matching source files found.", {"count": 0}

    payload = [_source_file_to_dict(f) for f in files]
    return _format_json_list(payload), {"count": len(payload)}


@evoloop_tool(summary_template="evoloop.tool_summary.query_security_findings")
async def query_security_findings(
    project_id: int | None = None,
    finding_type: str | None = None,
    severity: str | None = None,
    limit: int = 100,
) -> str:
    """Query SecurityFinding rows for the current project.

    Args:
        project_id: Optional project ID. Auto-detected from context if omitted.
        finding_type: Filter by vulnerability type.
        severity: Filter by severity (critical, high, medium, low).
        limit: Maximum number of rows to return.

    Returns:
        Formatted list of matching SecurityFinding records.
    """
    repo_id = await _resolve_repo_id(project_id)
    if repo_id is None:
        return "No active repository found for this project."

    async with session_scope() as session:
        stmt = select(SecurityFinding).join(
            SourceFile, SecurityFinding.source_file_id == SourceFile.id
        )
        stmt = stmt.where(SourceFile.repository_id == repo_id)
        if finding_type:
            stmt = stmt.where(SecurityFinding.finding_type == finding_type)
        if severity:
            stmt = stmt.where(SecurityFinding.severity == severity)
        stmt = stmt.order_by(SecurityFinding.id).limit(limit)
        result = await session.execute(stmt)
        findings = result.scalars().all()

    if not findings:
        return "No security findings found.", {"count": 0}

    payload = [_security_finding_to_dict(f) for f in findings]
    return _format_json_list(payload), {"count": len(payload)}


def _format_json_list(items: list[dict[str, Any]]) -> str:
    import json

    return json.dumps(items, indent=2, ensure_ascii=False)
