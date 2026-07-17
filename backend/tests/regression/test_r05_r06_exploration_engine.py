"""
R05 + R06: exploration/engine find_symbol / analyze_impact 回归测试

验证：
1. find_symbol 通过 RetrievalService.find_symbol_definition 查找
2. SQL 未找到时回退 FileSearcher
3. analyze_impact 通过 RetrievalService.find_usages 查找
4. 不再引用 graph_service（回归检测）

注意：_grep_find_symbol 内部使用 from app.core.tools import get_working_directory
作为惰性导入，因此打补丁需针对 app.core.tools.get_working_directory。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.codebase.exploration.engine import CodeExplorationEngine


class TestFindSymbol:
    """验证 find_symbol 符号查找。"""

    TOOL_MODULE = "app.core.tools"

    @pytest.fixture
    def engine(self):
        eng = CodeExplorationEngine()
        eng.lsp_manager = MagicMock()
        return eng

    @pytest.fixture
    def mock_retrieval(self):
        with patch(
            "app.domain.codebase.retrieval.service.RetrievalService.find_symbol_definition"
        ) as m:
            yield m

    async def test_find_symbol_sql_hit(self, engine, mock_retrieval):
        """SQL 找到符号定义时返回 SQL 来源的结果"""
        mock_retrieval.return_value = [
            {"full_name": "foo", "name": "foo", "type": "function", "file_path": "main.py", "score": None, "outgoing": []}
        ]
        result = await engine.find_symbol("foo", project_id=1)
        assert result is not None
        assert result["source"] == "sql"
        assert len(result["results"]) == 1

    async def test_find_symbol_sql_miss_fallback_grep(self, engine, mock_retrieval):
        """SQL 未找到时回退 FileSearcher"""
        mock_retrieval.return_value = []
        with patch(
            "app.domain.codebase.exploration.engine.FileSearcher.search_content",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = [{"file": "main.py", "line": 10, "content": "def foo():"}]
            with patch(f"{self.TOOL_MODULE}.get_working_directory", return_value="/fake/project"):
                result = await engine.find_symbol("foo", project_id=1, repo_path="/fake/project")
        assert result is not None
        assert result["source"] == "search_center"

    async def test_find_symbol_all_miss(self, engine, mock_retrieval):
        """SQL 和 grep 都未找到时返回 None"""
        mock_retrieval.return_value = []
        with patch("app.domain.codebase.exploration.engine.FileSearcher.search_content", new_callable=AsyncMock, return_value=[]) as ms:
            with patch(f"{self.TOOL_MODULE}.get_working_directory", return_value="/fake/project"):
                result = await engine.find_symbol("nonexistent", project_id=1, repo_path="/fake/project")
        assert result is None

    async def test_find_symbol_no_graph_reference(self, engine, mock_retrieval):
        """回归检测：不再引用 graph_service"""
        mock_retrieval.return_value = []
        with patch("app.domain.codebase.exploration.engine.FileSearcher.search_content", new_callable=AsyncMock, return_value=[]):
            with patch(f"{self.TOOL_MODULE}.get_working_directory", return_value="/fake/project"):
                result = await engine.find_symbol("test", project_id=1, repo_path="/fake/project")
                assert result is None


class TestAnalyzeImpact:
    """验证 analyze_impact 影响分析。"""

    @pytest.fixture
    def engine(self):
        eng = CodeExplorationEngine()
        eng.lsp_manager = MagicMock()
        return eng

    @pytest.fixture
    def mock_find_usages(self):
        with patch(
            "app.domain.codebase.retrieval.service.RetrievalService.find_usages"
        ) as m:
            yield m

    async def test_analyze_impact_returns_usages(self, engine, mock_find_usages):
        """analyze_impact 返回 find_usages 结果"""
        mock_find_usages.return_value = [
            {"source": "bar", "relation": "references", "file_path": "bar.py", "target": "foo"}
        ]
        result = await engine.analyze_impact("foo", project_id=1)
        assert len(result) == 1
        assert result[0]["source"] == "bar"

    async def test_analyze_impact_empty(self, engine, mock_find_usages):
        """无引用时返回空列表"""
        mock_find_usages.return_value = []
        result = await engine.analyze_impact("foo", project_id=1)
        assert result == []

    async def test_analyze_impact_no_graph_reference(self, engine, mock_find_usages):
        """回归检测：不因 graph_service 缺失而报错"""
        mock_find_usages.return_value = []
        result = await engine.analyze_impact("test", project_id=1)
        assert result == []
