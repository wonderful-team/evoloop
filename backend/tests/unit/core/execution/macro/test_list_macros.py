"""Tests for list_macros lifecycle and tool."""

from __future__ import annotations

import pytest

from app.core.execution.macro import lifecycle
from app.domain.tools.execution.list_macros import list_macros as list_macros_tool
from app.infrastructure.database import session_scope
from app.models.macro import Macro


async def _insert_macro(**kwargs) -> Macro:
    defaults = {
        "name": "macro",
        "description": "",
        "trigger_patterns": [],
        "parameters": [],
        "macro_script": "steps: []",
        "status": "verified",
        "is_active": True,
        "member_id": 0,
    }
    defaults.update(kwargs)
    macro = Macro(**defaults)
    async with session_scope() as db:
        db.add(macro)
        await db.flush()
        return macro


@pytest.mark.asyncio
@pytest.mark.db
async def test_list_macros_filters_by_project_id(_real_db):
    macro_a = await _insert_macro(name="a", project_id=1)
    _macro_b = await _insert_macro(name="b", project_id=2)

    result = await lifecycle.list_macros(project_id=1, status="verified")
    assert len(result) == 1
    assert result[0].id == macro_a.id


@pytest.mark.asyncio
@pytest.mark.db
async def test_list_macros_filters_by_namespace_and_entity(_real_db):
    await _insert_macro(name="web", namespace="web/github", entity="github")
    await _insert_macro(name="desktop", namespace="desktop/macos", entity="macos")

    result = await lifecycle.list_macros(
        namespace="web/github", entity="github", status="verified"
    )
    assert len(result) == 1
    assert result[0].name == "web"


@pytest.mark.asyncio
@pytest.mark.db
async def test_list_macros_query_searches_name_description_and_triggers(_real_db):
    await _insert_macro(name="Open Chrome", description="launch browser")
    await _insert_macro(name="Login", description="auth", trigger_patterns=["sign in"])
    await _insert_macro(name="Logout", description="exit")

    result = await lifecycle.list_macros(query="chrome", status="verified")
    assert len(result) == 1
    assert result[0].name == "Open Chrome"

    result = await lifecycle.list_macros(query="sign in", status="verified")
    assert len(result) == 1
    assert result[0].name == "Login"

    result = await lifecycle.list_macros(query="auth", status="verified")
    assert len(result) == 1
    assert result[0].name == "Login"


@pytest.mark.asyncio
@pytest.mark.db
async def test_list_macros_pagination(_real_db):
    for i in range(5):
        await _insert_macro(name=f"macro-{i}", project_id=42)

    result = await lifecycle.list_macros(project_id=42, limit=2, offset=0)
    assert len(result) == 2
    assert result[0].name == "macro-0"
    assert result[1].name == "macro-1"

    result = await lifecycle.list_macros(project_id=42, limit=2, offset=2)
    assert len(result) == 2
    assert result[0].name == "macro-2"


@pytest.mark.asyncio
@pytest.mark.db
async def test_list_macros_tool_uses_config_project_id(_real_db):
    await _insert_macro(name="proj-a", project_id=10)
    await _insert_macro(name="proj-b", project_id=20)

    result = await list_macros_tool(
        query="proj", config={"configurable": {"project_id": 10}}
    )
    assert "proj-a" in result
    assert "proj-b" not in result


@pytest.mark.asyncio
@pytest.mark.db
async def test_list_macros_tool_returns_empty_when_no_match(_real_db):
    await _insert_macro(name="exists", project_id=1)

    result = await list_macros_tool(
        query="missing", config={"configurable": {"project_id": 1}}
    )
    assert "No verified macros found" in result


@pytest.mark.asyncio
@pytest.mark.db
async def test_list_macros_tool_pagination(_real_db):
    for i in range(5):
        await _insert_macro(name=f"tool-macro-{i}", project_id=3)

    result = await list_macros_tool(
        query="tool-macro", limit=2, offset=0, config={"configurable": {"project_id": 3}}
    )
    assert "tool-macro-0" in result
    assert "tool-macro-1" in result
    assert "tool-macro-2" not in result


@pytest.mark.asyncio
@pytest.mark.db
async def test_list_macros_tool_global_context_only_sees_global_macros(_real_db):
    """When the Agent has no active project, it should only discover global macros."""
    await _insert_macro(name="global-macro", project_id=None)
    await _insert_macro(name="project-macro", project_id=42)

    result = await list_macros_tool(
        query="macro", config={"configurable": {"project_id": None}}
    )
    assert "global-macro" in result
    assert "project-macro" not in result
