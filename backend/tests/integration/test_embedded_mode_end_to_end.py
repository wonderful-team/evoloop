"""
Embedded Mode End-to-End Integration Tests (Phase 4)

Validates that real embedded-mode backend implementations can initialize,
perform CRUD operations, and interoperate correctly without requiring
external services (Neo4j, Redis, Meilisearch, PostgreSQL).

Run with:
    pytest tests/integration/test_embedded_mode_end_to_end.py --integration

The --integration flag prevents tests/conftest.py from applying unit-test-only
mocks (VectorStore, Queue, ResourceManager, SystemConfigService).
"""

import asyncio
import json
import importlib
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure EMBEDDED_MODE is active for these tests
os.environ.setdefault("EMBEDDED_MODE", "true")


@pytest.fixture(autouse=True)
def embedded_settings(monkeypatch):
    """Force embedded mode for every test in this module."""
    monkeypatch.setenv("EMBEDDED_MODE", "true")
    # Use a temporary directory for all file-based backends
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("EVOLOOP_APP_DATA_DIR", tmp)
        monkeypatch.setenv("LANCEDB_PATH", os.path.join(tmp, "lancedb"))
        # Re-import cache module to clear any pollution from unit-test patches
        import app.infrastructure.cache as _cache_mod

        _cache_mod._cache_instance = None
        importlib.reload(_cache_mod)
        yield tmp


class TestFileCacheLifecycle:
    """End-to-end validation of FileCache (embedded-mode cache backend)."""

    @pytest.mark.asyncio
    async def test_cache_set_get_delete(self, embedded_settings):
        from app.infrastructure.cache import get_cache

        cache = get_cache()
        await cache.set("test_key", "hello_embedded")
        result = await cache.get("test_key")
        assert result == "hello_embedded"

        await cache.delete("test_key")
        assert await cache.get("test_key") is None

    @pytest.mark.asyncio
    async def test_cache_hash_operations(self, embedded_settings):
        from app.infrastructure.cache import get_cache

        cache = get_cache()
        await cache.hset("test_hash", "field1", "value1")
        await cache.hset("test_hash", "field2", "value2")

        assert await cache.hget("test_hash", "field1") == "value1"
        assert await cache.hgetall("test_hash") == {"field1": "value1", "field2": "value2"}

        await cache.delete("test_hash")
        assert await cache.hgetall("test_hash") == {}

    @pytest.mark.asyncio
    async def test_cache_set_operations(self, embedded_settings):
        from app.infrastructure.cache import get_cache

        cache = get_cache()
        await cache.sadd("test_set", "a", "b", "c")
        assert await cache.sismember("test_set", "a") is True
        assert await cache.sismember("test_set", "z") is False
        assert set(await cache.smembers("test_set")) == {"a", "b", "c"}


class TestSQLiteFTSBackendLifecycle:
    """End-to-end validation of SQLiteFTSBackend (embedded-mode search)."""

    @pytest.fixture
    async def fts_backend(self, embedded_settings):
        from app.infrastructure.search.sqlite_fts import SQLiteFTSBackend

        db_path = os.path.join(embedded_settings, "search.db")
        backend = SQLiteFTSBackend(db_path=db_path)
        await backend.initialize()
        yield backend
        backend.close()

    @pytest.mark.asyncio
    async def test_index_and_search(self, fts_backend):
        from app.infrastructure.schemas import IndexDocumentRequest

        docs = [
            IndexDocumentRequest(doc_id="doc1", path="/doc1", title="Hello World", content="This is a test document about Python."),
            IndexDocumentRequest(doc_id="doc2", path="/doc2", title="Python Guide", content="Advanced Python programming techniques."),
            IndexDocumentRequest(doc_id="doc3", path="/doc3", title="JavaScript Basics", content="Introduction to JavaScript for beginners."),
        ]
        for doc in docs:
            await fts_backend.index_document(doc)

        results = await fts_backend.search("Python", limit=10)
        assert results.total >= 2
        ids = {r.doc_id for r in results.results}
        assert "doc1" in ids
        assert "doc2" in ids

    @pytest.mark.asyncio
    async def test_suggestions(self, fts_backend):
        from app.infrastructure.schemas import IndexDocumentRequest

        docs = [
            IndexDocumentRequest(doc_id="doc1", path="/doc1", title="Python Programming", content="..."),
            IndexDocumentRequest(doc_id="doc2", path="/doc2", title="Python Patterns", content="..."),
        ]
        for doc in docs:
            await fts_backend.index_document(doc)

        suggestions = await fts_backend.suggest("Pyt", limit=5)
        assert len(suggestions) >= 2

    @pytest.mark.asyncio
    async def test_delete_document(self, fts_backend):
        from app.infrastructure.schemas import IndexDocumentRequest

        doc = IndexDocumentRequest(doc_id="del1", path="/del1", title="Temporary", content="To be deleted")
        await fts_backend.index_document(doc)

        assert (await fts_backend.search("Temporary", limit=10)).total == 1

        await fts_backend.remove_document("del1")
        assert (await fts_backend.search("Temporary", limit=10)).total == 0


class TestFileGraphDriverLifecycle:
    """End-to-end validation of FileGraphDriver (embedded-mode graph)."""

    @pytest.fixture
    async def graph_driver(self, embedded_settings):
        from app.infrastructure.database.graph.file_graph import FileGraphDriver

        # FileGraphDriver.__init__ takes .parent of data_dir, so pass a subdir
        graph_subdir = os.path.join(embedded_settings, "graph")
        os.makedirs(graph_subdir, exist_ok=True)
        driver = FileGraphDriver(data_dir=graph_subdir)
        yield driver
        await driver.close()

    @pytest.mark.asyncio
    async def test_create_node_and_relationship(self, graph_driver):
        await graph_driver.upsert_node("Person", "id", {"name": "Alice", "id": "alice"})
        await graph_driver.upsert_node("Person", "id", {"name": "Bob", "id": "bob"})
        await graph_driver.link_nodes("Person", {"id": "alice"}, "Person", {"id": "bob"}, "KNOWS", {"since": 2020})

        # Verify via find_nodes and graph traversal
        alice = await graph_driver.find_nodes("Person", {"id": "alice"})
        assert len(alice) == 1
        assert alice[0]["name"] == "Alice"

        # Verify relationship exists via successors (internal IDs are label:node_id)
        assert "Person:bob" in list(graph_driver._graph.successors("Person:alice"))
        edge = graph_driver._graph.get_edge_data("Person:alice", "Person:bob")
        assert edge["type"] == "KNOWS"
        assert edge["since"] == 2020

    @pytest.mark.asyncio
    async def test_query_with_params(self, graph_driver):
        await graph_driver.upsert_node("Document", "id", {"title": "Doc A", "id": "doc_a"})
        await graph_driver.upsert_node("Tag", "id", {"name": "python", "id": "tag_py"})
        await graph_driver.link_nodes("Document", {"id": "doc_a"}, "Tag", {"id": "tag_py"}, "TAGGED")

        docs = await graph_driver.find_nodes("Document", {"title": "Doc A"})
        assert len(docs) == 1
        assert docs[0]["id"] == "doc_a"

    @pytest.mark.asyncio
    async def test_delete_node(self, graph_driver):
        await graph_driver.upsert_node("Item", "id", {"name": "to_delete", "id": "del_item"})
        assert len(await graph_driver.find_nodes("Item", {"id": "del_item"})) == 1

        await graph_driver.delete_nodes("Item", {"id": "del_item"})
        assert len(await graph_driver.find_nodes("Item", {"id": "del_item"})) == 0

    @pytest.mark.asyncio
    async def test_unsupported_cypher_raises(self, graph_driver):
        with pytest.raises(NotImplementedError):
            await graph_driver.execute_query("CALL algo.pageRank()")


class TestLanceVectorStoreLifecycle:
    """End-to-end validation of LanceVectorStore (embedded-mode vector storage)."""

    @pytest.fixture(autouse=True)
    def reset_lance_singleton(self, embedded_settings):
        """Reset LanceVectorStore singleton before each test."""
        from app.infrastructure.database.vector.lancedb_store import LanceVectorStore

        LanceVectorStore._instance = None
        yield
        LanceVectorStore._instance = None

    def test_upsert_and_search_code_chunks(self, embedded_settings):
        from app.infrastructure.database.vector import get_vector_store

        store = get_vector_store()
        # Use actual embedding dimension from settings
        from app.core.config import settings
        vec = [0.1] * settings.EMBEDDING_DIMENSIONS
        chunks = [
            {
                "file_path": "main.py",
                "content": "def hello(): pass",
                "start_line": 1,
                "end_line": 2,
                "identifier": "hello",
                "repository_id": "repo_1",
                "chunk_type": "function",
                "language": "python",
            }
        ]
        store.upsert_code_chunks(chunks, [vec])

        results = store.search_code(vec, repository_id="repo_1", top_k=5)
        assert len(results) == 1

    def test_delete_by_repository(self, embedded_settings):
        from app.infrastructure.database.vector import get_vector_store

        store = get_vector_store()
        from app.core.config import settings
        vec = [0.2] * settings.EMBEDDING_DIMENSIONS
        store.upsert_code_chunks(
            [
                {
                    "file_path": "a.py",
                    "content": "x",
                    "start_line": 1,
                    "end_line": 1,
                    "identifier": "x",
                    "repository_id": "repo_del",
                    "chunk_type": "function",
                    "language": "python",
                }
            ],
            [vec],
        )
        assert len(store.search_code(vec, repository_id="repo_del", top_k=5)) == 1

        store.delete_by_repository("repo_del")
        assert len(store.search_code(vec, repository_id="repo_del", top_k=5)) == 0


class TestLocalEventBusLifecycle:
    """End-to-end validation of LocalEventBus (embedded-mode event bus)."""

    @pytest.fixture
    def event_bus(self, embedded_settings):
        from app.core.engine.message.event_bus import LocalEventBus

        return LocalEventBus()

    @pytest.mark.asyncio
    async def test_publish_and_subscribe(self, event_bus):
        from app.utils.pubsub import in_memory_bus

        q = in_memory_bus.subscribe("test_channel")
        await event_bus.publish("test_channel", {"event": "test"})

        # Give event loop a chance to process
        await asyncio.sleep(0.05)

        assert not q.empty()
        msg = q.get_nowait()
        assert msg == {"event": "test"}
        in_memory_bus.unsubscribe("test_channel", q)

    @pytest.mark.asyncio
    async def test_publish_without_subscribers(self, event_bus):
        count = await event_bus.publish("empty_channel", {"event": "lonely"})
        assert count == 1  # LocalEventBus returns 1 even if no subscribers


class TestEmbeddedComponentsInterop:
    """Validate that multiple embedded backends can coexist and interoperate."""

    @pytest.mark.asyncio
    async def test_cache_search_graph_vector_together(self, embedded_settings):
        from app.infrastructure.cache import get_cache
        from app.infrastructure.database.graph.file_graph import FileGraphDriver
        from app.infrastructure.search.sqlite_fts import SQLiteFTSBackend
        from app.infrastructure.schemas import IndexDocumentRequest

        # 1. Cache a configuration value
        cache = get_cache()
        await cache.set("project_config", json.dumps({"name": "InteropTest"}))

        # 2. Index a document in FTS
        fts = SQLiteFTSBackend(db_path=os.path.join(embedded_settings, "interop_search.db"))
        await fts.initialize()
        await fts.index_document(
            IndexDocumentRequest(doc_id="p1", path="/p1", title="Interop Test", content="Testing all backends.")
        )

        # 3. Create a graph relationship
        graph_subdir = os.path.join(embedded_settings, "graph")
        os.makedirs(graph_subdir, exist_ok=True)
        graph = FileGraphDriver(data_dir=graph_subdir)
        await graph.upsert_node("Project", "id", {"name": "InteropTest", "id": "proj_1"})
        await graph.upsert_node("Document", "id", {"title": "Interop Test", "id": "doc_1"})
        await graph.link_nodes("Project", {"id": "proj_1"}, "Document", {"id": "doc_1"}, "CONTAINS")

        # 4. Verify all backends work
        assert json.loads(await cache.get("project_config"))["name"] == "InteropTest"
        assert (await fts.search("Testing", limit=5)).total == 1
        assert len(await graph.find_nodes("Project", {"name": "InteropTest"})) == 1
        assert "Document:doc_1" in list(graph._graph.successors("Project:proj_1"))

        fts.close()
        await graph.close()
