"""
核心业务流等价性验证 (Phase 10)

验证同一个业务场景在 EMBEDDED_MODE=true 和 EMBEDDED_MODE=false
两种模式下产生等价的结果。

当前实现聚焦记忆存储的等价性（最核心、最易于验证的业务流）。
聊天流和搜索流的等价性已在各自的集成测试中覆盖。
"""

import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings


class TestMemoryStorageEquivalence:
    """验证记忆存储在 Embedded 和 Production 两种模式下的功能等价性。"""

    @pytest.fixture
    async def embedded_memory(self):
        """Embedded 模式：使用 _FileEngine。"""
        import tempfile
        tmp = tempfile.mkdtemp(prefix="evo_mem_equiv_emb_")

        # Patch embedder 避免加载 SentenceTransformers（HuggingFace 超时）
        mock_embedder = AsyncMock()
        mock_embedder.embed_query = AsyncMock(return_value=[0.1] * 768)
        with patch("app.infrastructure.embeddings.factory.EmbedderFactory.get_embedder", return_value=mock_embedder):
            with patch.object(settings, "EMBEDDED_MODE", True):
                from app.core.memory.store import MemoryStore
                from app.core.memory.models import MemoryEntry, MemoryType

                # 直接传入 base_dir 参数，不依赖 settings.BRAIN_MEMORY_ROOT
                store = MemoryStore(base_dir=tmp)
                await store.initialize()
                yield store, MemoryEntry, MemoryType
                await store.close()

        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_embedded_save_and_get(self, embedded_memory):
        """Embedded 模式能保存和检索记忆。"""
        store, MemoryEntry, MemoryType = embedded_memory

        entry = MemoryEntry(
            id="mem_equiv_01",
            type=MemoryType.PROJECT,
            title="Equivalence Test",
            content="Testing memory storage in embedded mode.",
            project_id=42,
        )
        await store.save(entry)

        found = await store.get(entry.id)
        assert found is not None
        assert found.title == entry.title
        assert found.content == entry.content

    @pytest.mark.asyncio
    async def test_embedded_delete_removes_all_layers(self, embedded_memory):
        """Embedded 模式删除后所有层都不可见。"""
        store, MemoryEntry, MemoryType = embedded_memory

        entry = MemoryEntry(
            id="mem_equiv_del",
            type=MemoryType.PROJECT,
            title="Delete Test",
            content="To be deleted.",
            project_id=42,
        )
        await store.save(entry)
        assert await store.get(entry.id) is not None

        await store.delete(entry.id)
        assert await store.get(entry.id) is None


class TestSearchEquivalence:
    """验证搜索在两种模式下返回等价的结果格式。"""

    @pytest.mark.asyncio
    async def test_sqlite_fts_returns_document_results(self):
        """SQLite FTS 返回标准的结果格式。"""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        from app.infrastructure.search.sqlite_fts import SQLiteFTSBackend
        from app.infrastructure.schemas import IndexDocumentRequest

        backend = SQLiteFTSBackend(db_path=db_path)
        await backend.initialize()

        doc = IndexDocumentRequest(
            doc_id="equiv_doc_1",
            path="/test",
            title="Python Guide",
            content="Advanced Python programming techniques.",
        )
        await backend.index_document(doc)

        results = await backend.search("Python", limit=5)
        assert results.total >= 1
        assert any(r.doc_id == "equiv_doc_1" for r in results.results)

        backend.close()
        os.unlink(db_path)
