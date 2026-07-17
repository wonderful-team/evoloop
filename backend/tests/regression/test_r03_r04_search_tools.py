"""
R03 + R04: search_codebase / query_graph_natural_language 工具回归测试

验证：
1. search_codebase 调用 find_symbol_definition + find_usages + search
2. query_graph_natural_language 调用 multi_entity_query
3. 不再引用 graph_service（回归检测）

注意：@evoloop_tool 将函数包装为 StructuredTool，通过 .coroutine 访问原函数。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSearchCodebaseTool:
    """验证 search_codebase 工具路由。"""

    @pytest.fixture
    def tool(self):
        from app.domain.codebase.retrieval.tools import search_codebase
        return search_codebase

    @pytest.fixture
    def mock_retrieval(self):
        with patch(
            "app.domain.codebase.retrieval.tools.RetrievalService"
        ) as m:
            instance = MagicMock()
            instance.find_symbol_definition = AsyncMock(return_value=[])
            instance.find_usages = AsyncMock(return_value=[])
            instance.search = AsyncMock(return_value=[])
            m.return_value = instance
            yield instance

    @pytest.fixture
    def mock_resolve_pid(self):
        with patch(
            "app.domain.codebase.retrieval.tools.ContextManager.resolve_project_id"
        ) as m:
            m.return_value = 1
            yield m

    @pytest.fixture
    def mock_render(self):
        with patch(
            "app.domain.codebase.retrieval.tools.render_template"
        ) as m:
            m.return_value = "rendered"
            yield m

    async def test_search_codebase_calls_symbol_and_vector(
        self, tool, mock_retrieval, mock_resolve_pid, mock_render,
    ):
        """短查询同时触发符号查找和向量搜索"""
        result = await tool.coroutine(query="foo", operator="or")
        mock_retrieval.find_symbol_definition.assert_awaited_once_with("foo", project_id=1)
        mock_retrieval.find_usages.assert_awaited_once_with("foo", project_id=1)
        mock_retrieval.search.assert_awaited_once_with("foo", project_id=1, limit=5, operator="or")
        assert mock_render.called

    async def test_search_codebase_empty_results(
        self, tool, mock_retrieval, mock_resolve_pid, mock_render,
    ):
        """所有搜索返回空时模板正确渲染"""
        result = await tool.coroutine(query="nonexistent", operator="and")
        assert mock_render.called
        args, kwargs = mock_render.call_args
        assert kwargs.get("graph_result") is None
        assert kwargs.get("rag_results") == []

    async def test_search_no_graph_reference(self, tool, mock_retrieval, mock_resolve_pid, mock_render):
        """回归检测：运行不触发 graph_service 相关的 ImportError"""
        result = await tool.coroutine(query="test", operator="or")
        assert mock_render.called


class TestQueryGraphNLTool:
    """验证 query_graph_natural_language 工具路由。"""

    @pytest.fixture
    def tool(self):
        from app.domain.codebase.retrieval.tools import query_graph_natural_language
        return query_graph_natural_language

    @pytest.fixture
    def mock_retrieval(self, tool):
        with patch(
            "app.domain.codebase.retrieval.tools.RetrievalService"
        ) as m:
            instance = MagicMock()
            instance.multi_entity_query = AsyncMock(
                return_value="Graph Query Results for entities: pay, notify"
            )
            m.return_value = instance
            yield instance

    async def test_multi_entity_query_called(self, tool, mock_retrieval):
        """工具正确调用 multi_entity_query"""
        result = await tool.coroutine(
            question="调用关系",
            project_id=1,
            entities=["pay", "notify"],
            entity_operator="and",
        )
        mock_retrieval.multi_entity_query.assert_awaited_once_with(
            entities=["pay", "notify"],
            operator="and",
            question="调用关系",
            project_id=1,
        )
        assert "pay, notify" in result

    async def test_multi_entity_query_or_operator(self, tool, mock_retrieval):
        """OR 操作符正确传递"""
        await tool.coroutine(
            question="any",
            project_id=1,
            entities=["foo", "bar"],
            entity_operator="or",
        )
        mock_retrieval.multi_entity_query.assert_awaited_once()
        assert mock_retrieval.multi_entity_query.await_args.kwargs["operator"] == "or"
