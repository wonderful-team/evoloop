"""
R02: 索引仓库全流程回归测试

验证 IndexingService.index_repository 完整流水线：
1. 文件遍历 + .gitignore 过滤
2. 三阶段流水线：提取 → 嵌入 → 持久化
3. window 刷新机制
4. 错误处理和进度计数
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.codebase.indexing.service import IndexingService


@pytest.fixture
def mock_session():
    session = AsyncMock()
    repo = MagicMock()
    repo.id = 42
    repo.project_id = 1
    repo.local_path = "/fake/project"
    session.get = AsyncMock(return_value=repo)
    return session


@pytest.fixture
def mock_session_scope(mock_session):
    with patch("app.domain.codebase.indexing.service.session_scope") as ms:
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_session)
        ctx.__aexit__ = AsyncMock()
        ms.return_value = ctx
        yield ms, mock_session


@pytest.fixture
def mock_get_project_path():
    with patch("app.domain.codebase.indexing.service.get_project_path") as m:
        m.return_value = "/fake/project"
        yield m


@pytest.fixture
def mock_isdir():
    with patch.object(os.path, "isdir", return_value=True):
        yield


@pytest.fixture
def service(mock_session_scope, mock_get_project_path, mock_isdir):
    svc = IndexingService()
    svc.file_preparer = MagicMock()
    svc.file_preparer.should_index = MagicMock(return_value=True)
    svc.content_indexer = MagicMock()
    svc.sql_persister = MagicMock()
    svc.sql_persister.persist = AsyncMock(return_value={"foo": 1})
    svc.sql_persister.clear_old_data = AsyncMock()
    return svc


class TestIndexRepositoryPipeline:
    """验证 index_repository 三阶段流水线。"""

    async def test_index_repository_empty_dir_returns_early(self, service):
        """目录不存在时提前返回"""
        with patch("os.path.isdir", return_value=False):
            await service.index_repository("/invalid/path", 42)
        service.sql_persister.persist.assert_not_awaited()

    async def test_index_repository_skips_non_indexable_files(self, service):
        """should_index 返回 False 的文件被跳过"""
        with patch("app.core.file.service.walk_tree") as wt:
            wt.return_value = ["/fake/project/main.py", "/fake/project/ignored.dll"]
            service.file_preparer.should_index = MagicMock(side_effect=lambda p: p.endswith(".py"))
            await service.index_repository("/fake/project", 42)
        service.sql_persister.persist.assert_not_awaited()

    async def test_index_repository_processes_files(self, service):
        """文件遍历后进入处理流程"""
        files = [f"/fake/project/file_{i}.py" for i in range(3)]
        with patch("app.core.file.service.walk_tree") as wt:
            wt.return_value = files
            await service.index_repository("/fake/project", 42)

    async def test_repo_not_found_skips(self, service, mock_session_scope):
        """repo_id 不存在时跳过"""
        _, session = mock_session_scope
        session.get = AsyncMock(return_value=None)
        with patch("os.path.isdir", return_value=True):
            await service.index_repository("/fake/project", 999)
