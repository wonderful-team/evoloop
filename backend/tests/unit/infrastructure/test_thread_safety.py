"""
Thread-safety tests for infrastructure components used by Huey worker threads.

Huey runs with worker_type='thread' in embedded mode, so multiple OS threads
share the same process memory. These tests verify that the shared caches,
embedders, graph drivers, and vector stores behave correctly under concurrent
access without crashes or data corruption.
"""

import asyncio
import importlib
import json
import os
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.core.config import settings


class TestLocalEmbedderThreadSafety:
    """LocalEmbedder must be usable from multiple worker threads."""

    @pytest.fixture(autouse=True)
    def reset_embedder_cache(self):
        from app.infrastructure.embeddings.factory import EmbedderFactory
        from app.infrastructure.embeddings.local import LocalEmbedder

        EmbedderFactory.reset_cache()
        LocalEmbedder._shared_model_cache.clear()
        yield
        EmbedderFactory.reset_cache()
        LocalEmbedder._shared_model_cache.clear()

    def test_embedder_shared_across_threads_no_crash(self):
        """Two threads with independent event loops embed using the same instance."""
        from app.infrastructure.embeddings.local import LocalEmbedder

        fake_model = MagicMock()
        fake_model.encode = MagicMock(return_value=np.array([[0.1] * 768, [0.2] * 768]))
        embedder = LocalEmbedder()
        embedder._model = fake_model

        results = []
        errors = []

        def worker():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(
                    embedder.embed_documents(["hello", "world"])
                )
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Threads raised exceptions: {errors}"
        assert len(results) == 4
        for r in results:
            assert len(r) == 2
            assert len(r[0]) == 768

    def test_embedder_does_not_block_event_loop(self):
        """The brief _get_model fast path must not stall the loop."""
        from app.infrastructure.embeddings.local import LocalEmbedder

        embedder = LocalEmbedder()
        embedder._model = MagicMock()
        embedder._model.encode = MagicMock(return_value=np.array([[0.1] * 768]))

        async def background_ticker():
            ticks = 0
            for _ in range(20):
                await asyncio.sleep(0.01)
                ticks += 1
            return ticks

        async def main():
            embed_task = asyncio.create_task(embedder.embed_documents(["test"]))
            tick_task = asyncio.create_task(background_ticker())
            embed_result, ticks = await asyncio.gather(embed_task, tick_task)
            return embed_result, ticks

        result, ticks = asyncio.run(main())
        assert len(result) == 1
        assert ticks >= 18, f"Event loop was blocked: only {ticks} ticks"

    def test_concurrent_model_load_within_loop_loads_once(self):
        """Many coroutines racing to load the model must load it exactly once."""
        from app.infrastructure.embeddings.local import LocalEmbedder

        load_count = [0]
        fake_model = MagicMock()
        fake_model.encode = MagicMock(return_value=np.array([[0.1] * 768]))

        def slow_sentence_transformer(*_args, **_kwargs):
            load_count[0] += 1
            time.sleep(0.1)  # simulate slow load
            return fake_model

        embedder = LocalEmbedder()
        with patch(
            "sentence_transformers.SentenceTransformer",
            side_effect=slow_sentence_transformer,
        ):

            async def worker():
                return await embedder.embed_documents(["test"])

            async def main():
                tasks = [asyncio.create_task(worker()) for _ in range(20)]
                return await asyncio.gather(*tasks)

            results = asyncio.run(main())

        assert len(results) == 20
        assert load_count[0] == 1, f"Model loaded {load_count[0]} times instead of once"


class TestLocalEmbedderSingleFlightRegression:
    """Regression tests for the repeated model-loading bug."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        from app.infrastructure.embeddings.local import LocalEmbedder

        LocalEmbedder._shared_model_cache.clear()
        LocalEmbedder._loading_flags.clear()
        yield
        LocalEmbedder._shared_model_cache.clear()
        LocalEmbedder._loading_flags.clear()

    def test_many_threads_racing_load_model_once(self):
        """Many worker threads racing to embed must construct the model only once."""
        from app.infrastructure.embeddings.local import LocalEmbedder

        load_count = [0]
        fake_model = MagicMock()
        fake_model.encode = MagicMock(return_value=np.array([[0.1] * 768]))

        def slow_sentence_transformer(*_args, **_kwargs):
            load_count[0] += 1
            time.sleep(0.3)  # simulate slow model construction
            return fake_model

        results = []
        errors = []

        def worker():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                with patch(
                    "sentence_transformers.SentenceTransformer",
                    side_effect=slow_sentence_transformer,
                ):
                    result = loop.run_until_complete(
                        LocalEmbedder().embed_documents(["test"])
                    )
                    results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Threads raised exceptions: {errors}"
        assert len(results) == 6
        assert load_count[0] == 1, (
            f"Model loaded {load_count[0]} times across threads instead of once"
        )

    def test_cross_thread_model_load_loads_once(self):
        """Worker threads sharing one embedder instance must load the model once."""
        from app.infrastructure.embeddings.local import LocalEmbedder

        load_count = [0]
        fake_model = MagicMock()
        fake_model.encode = MagicMock(return_value=np.array([[0.1] * 768]))

        def slow_sentence_transformer(*_args, **_kwargs):
            load_count[0] += 1
            time.sleep(0.2)  # simulate slow load
            return fake_model

        embedder = LocalEmbedder()
        results = []
        errors = []

        def worker():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                with patch(
                    "sentence_transformers.SentenceTransformer",
                    side_effect=slow_sentence_transformer,
                ):
                    result = loop.run_until_complete(embedder.embed_documents(["test"]))
                    results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Threads raised exceptions: {errors}"
        assert len(results) == 4
        assert load_count[0] == 1, (
            f"Model loaded {load_count[0]} times across threads instead of once"
        )


class TestEmbedderFactoryCache:
    """EmbedderFactory._instances must be safe under concurrent creation."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        from app.infrastructure.embeddings.factory import EmbedderFactory

        EmbedderFactory.reset_cache()
        yield
        EmbedderFactory.reset_cache()

    def test_concurrent_get_embedder_creates_single_instance(self):
        """Multiple threads calling get_embedder() must share one cached instance."""
        from app.infrastructure.embeddings.factory import EmbedderFactory

        created = []

        def fake_create_embedder(_cls, _model_name, _cache_key):
            time.sleep(0.05)  # simulate slow model loading
            created.append(1)
            return MagicMock()

        with patch.object(
            EmbedderFactory, "_create_embedder", classmethod(fake_create_embedder)
        ):
            instances = []
            errors = []

            def worker():
                try:
                    instances.append(EmbedderFactory.get_embedder())
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert not errors, f"Exceptions during concurrent get_embedder: {errors}"
            assert len(instances) == 8
            assert len({id(i) for i in instances}) == 1, (
                "Threads got different embedder instances"
            )
            assert len(created) >= 1, "Embedder was never created"


class TestGraphManagerCache:
    """GraphManager._drivers must be safe under concurrent creation."""

    def test_concurrent_get_driver_creates_single_instance_per_key(self):
        """Multiple threads must get the same driver instance for the same key."""
        from app.infrastructure.database.graph.driver import GraphManager

        GraphManager._drivers.clear()
        created = []

        with patch.object(settings, "EMBEDDED_MODE", True):
            with patch(
                "app.infrastructure.database.graph.file_graph.FileGraphDriver"
            ) as MockDriver:
                instance = MagicMock()
                MockDriver.return_value = instance

                def slow_init(*_args, **_kwargs):
                    created.append(1)
                    time.sleep(0.02)
                    return instance

                MockDriver.side_effect = slow_init

                drivers = []
                errors = []

                def worker():
                    try:
                        drivers.append(
                            GraphManager.get_driver(project_path="/tmp/fake_project")
                        )
                    except Exception as e:
                        errors.append(e)

                threads = [threading.Thread(target=worker) for _ in range(8)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()

                assert not errors, f"Exceptions: {errors}"
                assert len(drivers) == 8
                assert len({id(d) for d in drivers}) == 1


class TestVectorStoreCache:
    """get_vector_store cache must be safe under concurrent creation."""

    def test_concurrent_get_vector_store_single_instance(self):
        """Multiple threads must get the same vector store for the same project."""
        # conftest.py replaces get_vector_store with a no-arg mock. Reload the
        # module to get the real implementation for this thread-safety test.
        import app.infrastructure.database.vector as vector_mod

        importlib.reload(vector_mod)
        real_get_vector_store = vector_mod.get_vector_store
        real_reset = vector_mod.reset_vector_store

        real_reset()

        with patch.object(settings, "EMBEDDED_MODE", True):
            with patch(
                "app.infrastructure.database.vector.lancedb_store.LanceVectorStore"
            ) as MockStore:
                instance = MagicMock()
                MockStore.return_value = instance

                stores = []
                errors = []

                def worker():
                    try:
                        stores.append(
                            real_get_vector_store(project_path="/tmp/fake_project")
                        )
                    except Exception as e:
                        errors.append(e)

                threads = [threading.Thread(target=worker) for _ in range(8)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()

                assert not errors, f"Exceptions: {errors}"
                assert len(stores) == 8
                assert len({id(s) for s in stores}) == 1


class TestFileGraphDriverConcurrency:
    """FileGraphDriver must not corrupt JSON when mutated from multiple threads."""

    @pytest.fixture
    def graph_driver(self):
        from app.infrastructure.database.graph.file_graph import FileGraphDriver

        with tempfile.TemporaryDirectory() as tmpdir:
            graph_subdir = os.path.join(tmpdir, "graph")
            os.makedirs(graph_subdir, exist_ok=True)
            driver = FileGraphDriver(data_dir=graph_subdir)
            yield driver

    @pytest.mark.asyncio
    async def test_concurrent_upsert_node_saves_valid_json(self, graph_driver):
        """Many threads upserting nodes concurrently must leave a valid graph file."""
        driver = graph_driver
        errors = []

        async def worker(worker_id):
            try:
                for i in range(20):
                    await driver.upsert_node(
                        "File",
                        "path",
                        {
                            "path": f"src/file_{worker_id}_{i}.py",
                            "project_id": 1,
                            "lines": i,
                        },
                    )
            except Exception as e:
                errors.append(e)

        threads = []
        for w in range(4):
            loop = asyncio.new_event_loop()
            t = threading.Thread(
                target=lambda loop_, wid: loop_.run_until_complete(worker(wid)),
                args=(loop, w),
            )
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent upsert raised: {errors}"

        # Verify the saved JSON is valid
        with open(driver.graph_file, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["nodes"]) == 80  # 4 workers * 20 unique nodes


class TestLanceVectorStoreConcurrency:
    """LanceVectorStore delete-then-add sequences must be atomic per store."""

    @pytest.fixture
    def vector_store(self):
        from app.infrastructure.database.vector.lancedb_store import LanceVectorStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LanceVectorStore(tmpdir)
            yield store

    def test_concurrent_upsert_same_file_no_duplicates(self, vector_store):
        """Concurrent upserts of the same file must not leave duplicate chunks."""
        store = vector_store
        errors = []

        def worker(worker_id):
            try:
                chunks = [
                    {
                        "content": f"content from worker {worker_id}",
                        "file_path": "src/shared.py",
                        "repository_id": "1",
                        "chunk_type": "module",
                        "identifier": "shared",
                        "start_line": 1,
                        "end_line": 1,
                        "language": "python",
                    }
                ]
                embeddings = [[0.1] * settings.EMBEDDING_DIMENSIONS]
                store.upsert_code_chunks(chunks, embeddings)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent upsert raised: {errors}"
        rows = store.code_table.to_pandas().to_dict("records")
        file_rows = [r for r in rows if r["file_path"] == "src/shared.py"]
        assert len(file_rows) == 1, (
            f"Expected 1 chunk for shared.py, got {len(file_rows)}"
        )


class TestIndexingManagerThreadSafety:
    """IndexingManager cancellation and status tracking must be thread-safe."""

    def test_cancel_from_different_thread_does_not_crash(self):
        """Cancel called from one thread while check is on another must be safe."""
        from app.domain.codebase.indexing.manager import IndexingManager

        manager = IndexingManager()
        manager._cancel_flags[1] = threading.Event()
        errors = []

        def cancel_worker():
            try:
                manager.cancel_indexing(1)
            except Exception as e:
                errors.append(e)

        def check_worker():
            try:
                manager._check_cancelled(1)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=cancel_worker),
            threading.Thread(target=check_worker),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread-safety error: {errors}"
