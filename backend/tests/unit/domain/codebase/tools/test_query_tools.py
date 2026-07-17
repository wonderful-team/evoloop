"""Integration tests for codebase index query tools."""

from __future__ import annotations

import json

import pytest

from app.domain.codebase.tools.query_tools import (
    query_code_chunks,
    query_code_relations,
    query_security_findings,
    query_source_files,
)
from app.infrastructure.database import session_scope
from app.models import (
    CodeChunk,
    CodeEntity,
    CodeRelation,
    Repository,
    SecurityFinding,
    SourceFile,
)


async def _seed_project() -> int:
    """Create a Repository with project_id and one SourceFile."""
    async with session_scope() as db:
        repo = Repository(
            name="test-repo",
            url="local",
            sync_status="SYNCED",
            project_id=42,
        )
        db.add(repo)
        await db.flush()

        source = SourceFile(
            repository_id=repo.id,
            path="src/main.py",
            checksum="0" * 64,
            scan_status="completed",
        )
        db.add(source)
        await db.flush()
        return repo.id, source.id


@pytest.mark.asyncio
async def test_query_code_chunks_by_api_route(_real_db):
    """query_code_chunks filters by is_api_route and project_id."""
    repo_id, source_file_id = await _seed_project()

    async with session_scope() as db:
        db.add(
            CodeChunk(
                source_file_id=source_file_id,
                chunk_type="function",
                identifier="get_user",
                start_line=1,
                end_line=10,
                content="def get_user(): ...",
                is_api_route=True,
                api_method="GET",
                api_path="/users/{id}",
            )
        )
        db.add(
            CodeChunk(
                source_file_id=source_file_id,
                chunk_type="function",
                identifier="_internal_helper",
                start_line=12,
                end_line=15,
                content="def _internal_helper(): ...",
            )
        )
        await db.flush()

    result = await query_code_chunks(project_id=42, is_api_route=True)
    data = json.loads(result)
    assert len(data) == 1
    assert data[0]["identifier"] == "get_user"
    assert data[0]["api_method"] == "GET"


@pytest.mark.asyncio
async def test_query_source_files_by_scan_status(_real_db):
    """query_source_files filters by scan_status and project_id."""
    await _seed_project()

    result = await query_source_files(project_id=42, scan_status="completed")
    data = json.loads(result)
    assert len(data) == 1
    assert data[0]["path"] == "src/main.py"
    assert data[0]["scan_status"] == "completed"


@pytest.mark.asyncio
async def test_query_security_findings_by_severity(_real_db):
    """query_security_findings filters by severity and project_id."""
    repo_id, source_file_id = await _seed_project()

    async with session_scope() as db:
        db.add(
            SecurityFinding(
                source_file_id=source_file_id,
                finding_type="sql_injection",
                severity="high",
                description="Raw SQL in controller",
            )
        )
        db.add(
            SecurityFinding(
                source_file_id=source_file_id,
                finding_type="hardcoded_secret",
                severity="low",
                description="Test key",
            )
        )
        await db.flush()

    result = await query_security_findings(project_id=42, severity="high")
    data = json.loads(result)
    assert len(data) == 1
    assert data[0]["finding_type"] == "sql_injection"


@pytest.mark.asyncio
async def test_query_code_relations_by_type(_real_db):
    """query_code_relations filters by relation_type and project_id."""
    repo_id, source_file_id = await _seed_project()

    async with session_scope() as db:
        source = CodeEntity(
            file_id=source_file_id,
            name="caller",
            type="function",
            full_name="src.main.caller",
            start_line=1,
            end_line=5,
        )
        target = CodeEntity(
            file_id=source_file_id,
            name="callee",
            type="function",
            full_name="src.main.callee",
            start_line=7,
            end_line=12,
        )
        db.add(source)
        db.add(target)
        await db.flush()

        db.add(
            CodeRelation(
                source_entity_id=source.id,
                target_entity_id=target.id,
                relation_type="calls",
                confidence="EXTRACTED",
            )
        )
        await db.flush()

    result = await query_code_relations(project_id=42, relation_type="calls")
    data = json.loads(result)
    assert len(data) == 1
    assert data[0]["relation_type"] == "calls"
    assert data[0]["target_entity_id"] == target.id
