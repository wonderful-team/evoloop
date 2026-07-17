"""Unit tests for app.core.tools.manager.ToolManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.engine.state import AgentState
from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket
from app.core.tools.manager import ToolManager


def _tool(name: str) -> MagicMock:
    t = MagicMock()
    t.name = name
    return t


def _fresh_manager() -> ToolManager:
    """Return a fresh ToolManager instance bypassing the singleton cache."""
    instance = object.__new__(ToolManager)
    return instance


@pytest.fixture
def manager() -> ToolManager:
    return _fresh_manager()


@pytest.fixture
def static_tools() -> list[MagicMock]:
    return [_tool("read_file"), _tool("write_file"), _tool("execute_command")]


@pytest.fixture
def native_tool_map() -> dict[str, MagicMock]:
    return {
        "read_file": _tool("read_file"),
        "write_file": _tool("write_file"),
        "write_wiki_page": _tool("write_wiki_page"),
        "query_code_chunks": _tool("query_code_chunks"),
        "query_code_relations": _tool("query_code_relations"),
    }


@pytest.fixture
def _patched_registry(static_tools, native_tool_map):
    with (
        patch("app.core.tools.registry.get_node_tools", return_value=static_tools),
        patch("app.core.tools.registry.get_tool_map", return_value=native_tool_map),
    ):
        yield


@pytest.fixture
def _patched_mcp():
    with patch(
        "app.core.mcp.mcp_client_manager",
        new=MagicMock(aget_all_tools=AsyncMock(return_value=[])),
    ):
        yield


@pytest.mark.asyncio
async def test_allowlist_filters_static_tools(
    manager: ToolManager,
    _patched_registry,
    _patched_mcp,
):
    """When agent_config.tools is set, only allowed tools are returned."""
    ticket = ExecutionTicket(
        ticket_type="task",
        topic="test",
        reason="test",
        agent_config=AgentRuntimeConfig(tools=["read_file"]),
    )
    state = AgentState(messages=[], ticket=ticket)

    tools = await manager.get_node_tools("worker", state)
    names = {t.name for t in tools}

    assert names == {"read_file"}
    assert "write_file" not in names
    assert "execute_command" not in names


@pytest.mark.asyncio
async def test_dynamic_native_tool_hydrated(
    manager: ToolManager,
    _patched_registry,
    _patched_mcp,
):
    """Native tools requested in agent_config.tools but absent from the static
    worker baseline are still hydrated and returned."""
    ticket = ExecutionTicket(
        ticket_type="task",
        topic="test",
        reason="test",
        agent_config=AgentRuntimeConfig(tools=["query_code_chunks"]),
    )
    state = AgentState(messages=[], ticket=ticket)

    tools = await manager.get_node_tools("worker", state)
    names = {t.name for t in tools}

    assert names == {"query_code_chunks"}


@pytest.mark.asyncio
async def test_supervisor_not_filtered_by_allowlist(
    manager: ToolManager,
    _patched_registry,
    _patched_mcp,
):
    """Supervisor always sees the full static pool even if a tool list is present."""
    ticket = ExecutionTicket(
        ticket_type="task",
        topic="test",
        reason="test",
        agent_config=AgentRuntimeConfig(tools=["read_file"]),
    )
    state = AgentState(messages=[], ticket=ticket)

    tools = await manager.get_node_tools("supervisor", state)
    names = {t.name for t in tools}

    assert "read_file" in names
    assert "write_file" in names
    assert "execute_command" in names


@pytest.mark.asyncio
async def test_write_wiki_page_replaces_write_file(
    manager: ToolManager,
    _patched_registry,
    _patched_mcp,
):
    """When write_wiki_page is authorized, write_file is removed to avoid ambiguity."""
    ticket = ExecutionTicket(
        ticket_type="task",
        topic="test",
        reason="test",
        agent_config=AgentRuntimeConfig(tools=["write_wiki_page", "read_file"]),
    )
    state = AgentState(messages=[], ticket=ticket)

    tools = await manager.get_node_tools("worker", state)
    names = {t.name for t in tools}

    assert "write_wiki_page" in names
    assert "read_file" in names
    assert "write_file" not in names


@pytest.mark.asyncio
async def test_no_state_uses_static_pool(
    manager: ToolManager,
    _patched_registry,
):
    """Without state, the manager returns the static node pool unchanged."""
    tools = await manager.get_node_tools("worker", None)
    names = {t.name for t in tools}

    assert names == {"read_file", "write_file", "execute_command"}
