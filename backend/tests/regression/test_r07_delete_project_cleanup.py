"""
R07: 删除项目清理回归测试

验证 delete_project 处理后：
1. SQL 数据通过 Repository cascade 删除
2. 向量存储数据被清理
3. 不再引用 graph 清理代码
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestDeleteProjectCleanup:
    """验证项目删除后的数据和图清理回归。"""

    PROJECTS_MODULE = "app.api.routes.projects"

    @pytest.fixture
    def mock_repo(self):
        repo = MagicMock()
        repo.id = 42
        repo.project_id = 123
        repo.local_path = "/workspace/test-project"
        return repo

    @pytest.fixture
    def mock_session(self, mock_repo):
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [mock_repo]
        session.execute.return_value = result_mock
        session.get = AsyncMock(return_value=mock_repo)
        return session

    @pytest.fixture
    def mock_session_scope(self, mock_session):
        with patch(f"{self.PROJECTS_MODULE}.session_scope") as ms:
            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock(return_value=mock_session)
            async def _aexit(*_):
                await mock_session.commit()
                return False
            ctx.__aexit__ = _aexit
            ms.return_value = ctx
            yield ms

    @pytest.fixture
    def mock_cloud_success(self):
        with patch(f"{self.PROJECTS_MODULE}.evocloud_manager") as m:
            m.api.delete_project = AsyncMock(return_value={"code": 0, "message": "ok"})
            m.invalidate_projects_cache = MagicMock()
            yield m

    @pytest.fixture
    def mock_indexing_manager(self):
        with patch(f"{self.PROJECTS_MODULE}.indexing_manager") as m:
            m.stop_watching = AsyncMock()
            yield m

    @pytest.fixture
    def mock_vector_store(self):
        vs = MagicMock()
        vs.delete_by_repository = MagicMock(return_value=5)
        with patch(f"{self.PROJECTS_MODULE}.get_vector_store", return_value=vs):
            yield vs

    async def test_delete_project_cleans_sql_and_vector(
        self, mock_cloud_success, mock_session_scope, mock_session, mock_repo,
        mock_indexing_manager, mock_vector_store,
    ):
        """删除项目后 SQL 和向量数据被清理"""
        from app.api.routes.projects import delete_project

        result = await delete_project(123, None)

        assert result.status == "success"
        # SQL: repo cascade delete
        mock_session.delete.assert_awaited_once_with(mock_repo)
        # Vector: delete_by_repository
        mock_vector_store.delete_by_repository.assert_called_once_with("42")

    async def test_delete_project_no_graph_cleanup_reference(
        self, mock_cloud_success, mock_session_scope, mock_session, mock_repo,
        mock_indexing_manager, mock_vector_store,
    ):
        """回归检测：delete_project 完成时不因 graph_service 缺失而报错"""
        from app.api.routes.projects import delete_project
        result = await delete_project(123, None)
        assert result.status == "success"

    async def test_delete_project_no_local_repo(
        self, mock_cloud_success, mock_session_scope, mock_session, mock_indexing_manager,
    ):
        """无本地 repo 时优雅跳过"""
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        from app.api.routes.projects import delete_project

        result = await delete_project(123, None)
        assert result.status == "success"
        mock_indexing_manager.stop_watching.assert_not_awaited()
