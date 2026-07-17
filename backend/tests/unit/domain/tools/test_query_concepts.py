"""Tests for query_concepts tool (C2)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_search_concepts_success():
    from types import SimpleNamespace
    mock_concepts = [
        SimpleNamespace(name="C1", description="D1"),
        SimpleNamespace(name="C2", description="D2"),
    ]
    mock_container = MagicMock()
    mock_container.memory_manager.search_concepts = AsyncMock(return_value=mock_concepts)

    with (
        patch('app.core.memory.lifespan.MemoryLifespanManager.is_initialized', return_value=True),
        patch('app.core.memory.lifespan.MemoryLifespanManager.get_container', return_value=mock_container),
    ):
        from app.domain.tools.project_knowledge import _search_concepts
        results = await _search_concepts("test", project_id=42)
        assert len(results) == 2
        assert results[0]["name"] == "C1"
        assert results[0]["source"] == "project"
        assert results[1]["name"] == "C2"


@pytest.mark.asyncio
async def test_search_concepts_global_source():
    from types import SimpleNamespace
    mock_concepts = [
        SimpleNamespace(name="G1", description="GD1"),
    ]
    mock_container = MagicMock()
    mock_container.memory_manager.search_concepts = AsyncMock(return_value=mock_concepts)

    with (
        patch('app.core.memory.lifespan.MemoryLifespanManager.is_initialized', return_value=True),
        patch('app.core.memory.lifespan.MemoryLifespanManager.get_container', return_value=mock_container),
    ):
        from app.domain.tools.project_knowledge import _search_concepts
        results = await _search_concepts("test", project_id=0)
        assert results[0]["source"] == "global"


@pytest.mark.asyncio
async def test_search_concepts_failure_returns_empty():
    mock_container = MagicMock()
    mock_container.memory_manager.search_concepts = AsyncMock(side_effect=ValueError("fail"))

    with (
        patch('app.core.memory.lifespan.MemoryLifespanManager.is_initialized', return_value=True),
        patch('app.core.memory.lifespan.MemoryLifespanManager.get_container', return_value=mock_container),
    ):
        from app.domain.tools.project_knowledge import _search_concepts
        results = await _search_concepts("test", project_id=42)
        assert results == []


@pytest.mark.asyncio
async def test_search_concepts_initializes_lifespan():
    mock_container = MagicMock()
    mock_container.memory_manager.search_concepts = AsyncMock(return_value=[])

    with (
        patch('app.core.memory.lifespan.MemoryLifespanManager.is_initialized', side_effect=[False, True]),
        patch('app.core.memory.lifespan.MemoryLifespanManager.ainitialize', new_callable=AsyncMock) as mock_init,
        patch('app.core.memory.lifespan.MemoryLifespanManager.get_container', return_value=mock_container),
    ):
        from app.domain.tools.project_knowledge import _search_concepts
        results = await _search_concepts("test", project_id=42)
        assert results == []
        mock_init.assert_awaited_once()


@pytest.mark.asyncio
async def test_query_concepts_global_mode():
    with patch('app.core.context.manager.ContextManager') as MockCtxMgr:
        ctx = MagicMock()
        ctx.project_id = 0
        MockCtxMgr.current.return_value = ctx

        from app.domain.tools.project_knowledge import query_concepts
        result = await query_concepts(query="test")
        assert "Global mode" in result


@pytest.mark.asyncio
async def test_query_concepts_with_results():
    from types import SimpleNamespace
    mock_container = MagicMock()
    mock_container.memory_manager.search_concepts = AsyncMock(return_value=[
        SimpleNamespace(name="ArchPattern", description="Clean Architecture layers"),
    ])

    with (
        patch('app.core.context.manager.ContextManager') as MockCtxMgr,
        patch('app.core.memory.lifespan.MemoryLifespanManager.is_initialized', return_value=True),
        patch('app.core.memory.lifespan.MemoryLifespanManager.get_container', return_value=mock_container),
    ):
        ctx = MagicMock()
        ctx.project_id = 42
        MockCtxMgr.current.return_value = ctx

        from app.domain.tools.project_knowledge import query_concepts
        result = await query_concepts(query="arch")
        assert "Project Concepts" in result
        assert "ArchPattern" in result
        assert "project_id=42" in result


@pytest.mark.asyncio
async def test_query_concepts_no_results():
    mock_container = MagicMock()
    mock_container.memory_manager.search_concepts = AsyncMock(return_value=[])

    with (
        patch('app.core.context.manager.ContextManager') as MockCtxMgr,
        patch('app.core.memory.lifespan.MemoryLifespanManager.is_initialized', return_value=True),
        patch('app.core.memory.lifespan.MemoryLifespanManager.get_container', return_value=mock_container),
    ):
        ctx = MagicMock()
        ctx.project_id = 42
        MockCtxMgr.current.return_value = ctx

        from app.domain.tools.project_knowledge import query_concepts
        result = await query_concepts(query="nonexistent")
        assert "No concept knowledge found" in result
        assert "42" in result


@pytest.mark.asyncio
async def test_query_concepts_only_project_results():
    from types import SimpleNamespace
    mock_container = MagicMock()
    mock_container.memory_manager.search_concepts = AsyncMock()
    mock_container.memory_manager.search_concepts.side_effect = [
        [SimpleNamespace(name="C1", description="D1")],
        [],
    ]

    with (
        patch('app.core.context.manager.ContextManager') as MockCtxMgr,
        patch('app.core.memory.lifespan.MemoryLifespanManager.is_initialized', return_value=True),
        patch('app.core.memory.lifespan.MemoryLifespanManager.get_container', return_value=mock_container),
    ):
        ctx = MagicMock()
        ctx.project_id = 42
        MockCtxMgr.current.return_value = ctx

        from app.domain.tools.project_knowledge import query_concepts
        result = await query_concepts(query="")
        assert "Project Concepts (1)" in result
        assert "Global Concepts" not in result


@pytest.mark.asyncio
async def test_query_concepts_only_global_results():
    from types import SimpleNamespace
    mock_container = MagicMock()
    mock_container.memory_manager.search_concepts = AsyncMock()
    mock_container.memory_manager.search_concepts.side_effect = [
        [],
        [SimpleNamespace(name="G1", description="GD1")],
    ]

    with (
        patch('app.core.context.manager.ContextManager') as MockCtxMgr,
        patch('app.core.memory.lifespan.MemoryLifespanManager.is_initialized', return_value=True),
        patch('app.core.memory.lifespan.MemoryLifespanManager.get_container', return_value=mock_container),
    ):
        ctx = MagicMock()
        ctx.project_id = 42
        MockCtxMgr.current.return_value = ctx

        from app.domain.tools.project_knowledge import query_concepts
        result = await query_concepts(query="")
        assert "Global Concepts" in result
        assert "Project Concepts" not in result
