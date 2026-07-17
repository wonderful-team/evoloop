"""
R01: 索引文件后 SQL 数据一致性回归测试

验证 IndexingService.index_file 正确调用流水线组件：
1. FilePreparer → ContentIndexer → SQLPersister 链路完整
2. SQL 持久化接收正确的 indexed 数据
3. 向量存储 upsert 在 embeddings 存在时触发
4. GraphSyncer 不再被引用（回归检测）

策略：使用 prepared_override / indexed_override 绕过真实文件操作，
聚焦 SQL 持久化和向量存储的调用验证。
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.codebase.indexing.service import IndexingService
from app.domain.codebase.schemas import (
    ExtractedEntity,
    ExtractedRelation,
    IndexedContent,
    PreparedFile,
)
from app.models.codebase import Repository, SourceFile
from app.models.schemas.document import Document


@pytest.fixture
def fake_repo():
    return Repository(id=42, project_id=1, local_path="/fake/project", name="test", url="local")


@pytest.fixture
def fake_source_file():
    return SourceFile(id=1, path="main.py", repository_id=42)


@pytest.fixture
def mock_session(fake_repo):
    session = AsyncMock()
    session.get = AsyncMock(return_value=fake_repo)
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
    svc.content_indexer = MagicMock()
    svc.sql_persister = MagicMock()
    svc.file_preparer.create_or_update_source_file = AsyncMock(
        return_value=MagicMock(id=1, path="main.py")
    )
    svc.sql_persister.clear_old_data = AsyncMock()
    svc.sql_persister.persist = AsyncMock(return_value={"foo": 1})
    return svc


class TestIndexFilePipeline:
    """验证 index_file 流水线组件调用和 SQL 一致性。"""

    async def test_full_pipeline(self, service, mock_session_scope, fake_repo, fake_source_file):
        """完整流水线调用: 所有组件按序执行"""
        _, session = mock_session_scope
        prepared = PreparedFile(
            file_path="/fake/project/main.py",
            content="def foo(): pass",
            rel_path="main.py",
            checksum="abc123",
            source_file=fake_source_file,
            is_new=True,
            repo=fake_repo,
        )
        indexed = IndexedContent(
            documents=[Document(content="def foo(): pass")],
            entities=[ExtractedEntity(name="foo", type="function", full_name="foo", start_line=1, end_line=1)],
            relations=[ExtractedRelation(source_full_name="foo", target_full_name="bar", relation_type="calls")],
            embeddings=[[0.1, 0.2, 0.3]],
            file_summary_doc=Document(content="file summary"),
        )

        with patch("app.domain.codebase.indexing.service.get_vector_store") as mock_vs_getter:
            vs = MagicMock()
            mock_vs_getter.return_value = vs
            await service.index_file(
                "/fake/project/main.py", 42,
                prepared_override=prepared,
                indexed_override=indexed,
            )

        service.sql_persister.clear_old_data.assert_awaited_once()
        service.sql_persister.persist.assert_awaited_once()
        vs.upsert_code_chunks.assert_called_once()

    async def test_skip_vector_when_no_embeddings(
        self, service, mock_session_scope, fake_repo, fake_source_file,
    ):
        """embeddings 为空时跳过向量 upsert"""
        prepared = PreparedFile(
            file_path="/fake/project/main.py",
            content="def foo(): pass",
            rel_path="main.py",
            checksum="abc123",
            source_file=fake_source_file,
            is_new=True,
            repo=fake_repo,
        )
        indexed = IndexedContent(
            documents=[], entities=[], relations=[], embeddings=[],
            file_summary_doc=Document(content="file summary"),
        )

        with patch("app.domain.codebase.indexing.service.get_vector_store") as mock_vs_getter:
            await service.index_file(
                "/fake/project/main.py", 42,
                prepared_override=prepared,
                indexed_override=indexed,
            )

        mock_vs_getter.return_value.upsert_code_chunks.assert_not_called()

    async def test_persister_receives_correct_data(
        self, service, mock_session_scope, fake_repo, fake_source_file,
    ):
        """sql_persister.persist 接收到正确的 indexed 和 source_file"""
        prepared = PreparedFile(
            file_path="/fake/project/main.py",
            content="def foo(): pass",
            rel_path="main.py",
            checksum="abc123",
            source_file=fake_source_file,
            is_new=True,
            repo=fake_repo,
        )
        indexed = IndexedContent(
            documents=[],
            entities=[ExtractedEntity(name="foo", type="function", full_name="foo", start_line=1, end_line=1)],
            relations=[], embeddings=[],
            file_summary_doc=Document(content="file summary"),
        )

        with patch("app.domain.codebase.indexing.service.get_vector_store"):
            await service.index_file(
                "/fake/project/main.py", 42,
                prepared_override=prepared,
                indexed_override=indexed,
            )

        call_args = service.sql_persister.persist.await_args
        assert call_args is not None
        actual_indexed, actual_source_file, actual_session = call_args.args
        assert actual_indexed is indexed
        assert actual_source_file is not None

    async def test_repo_not_found_aborts(self, service, mock_session_scope):
        """repo_id 不存在时提前返回"""
        _, session = mock_session_scope
        session.get = AsyncMock(return_value=None)

        await service.index_file("/fake/project/nonexistent.py", 999)

        service.sql_persister.persist.assert_not_awaited()

    async def test_no_graph_syncer_reference(self, service, mock_session_scope, fake_repo, fake_source_file):
        """回归检测: index_file 不再引用 GraphSyncer，执行不报错"""
        prepared = PreparedFile(
            file_path="/fake/project/main.py",
            content="def foo(): pass", rel_path="main.py",
            checksum="abc123",
            source_file=fake_source_file,
            is_new=True, repo=fake_repo,
        )
        indexed = IndexedContent(
            documents=[], entities=[], relations=[], embeddings=[],
            file_summary_doc=Document(content="file summary"),
        )
        with patch("app.domain.codebase.indexing.service.get_vector_store"):
            await service.index_file(
                "/fake/project/main.py", 42,
                prepared_override=prepared,
                indexed_override=indexed,
            )
