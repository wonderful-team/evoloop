"""
Phase 1 Tests - Stability & Foundation Optimization

Covers:
- T-1.1: SQLite WAL + Connection Pool
- T-1.2: Storage path configurability
- T-1.3: list_documents batch tag loading
- T-1.4: Maintenance report persistence
"""

import json
import os
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestConnectionPool:
    """T-1.1: Verify thread-safe connection pool with WAL mode"""

    def test_pool_acquire_returns_connection(self):
        from app.domain.knowledge.services.connection_pool import KnowledgeConnectionPool

        db_path = Path(tempfile.mktemp(suffix=".db"))
        pool = KnowledgeConnectionPool(db_path)

        with pool.acquire() as conn:
            # Should be able to execute
            result = conn.execute("SELECT 1").fetchone()
            assert result[0] == 1

        pool.close_all()

    def test_pool_wal_mode_enabled(self):
        from app.domain.knowledge.services.connection_pool import KnowledgeConnectionPool

        db_path = Path(tempfile.mktemp(suffix=".db"))
        pool = KnowledgeConnectionPool(db_path)

        with pool.acquire() as conn:
            result = conn.execute("PRAGMA journal_mode").fetchone()
            assert result[0].lower() == "wal"

        pool.close_all()

    def test_pool_concurrent_access(self):
        """Multiple threads should be able to use the pool simultaneously."""
        from app.domain.knowledge.services.connection_pool import KnowledgeConnectionPool

        db_path = Path(tempfile.mktemp(suffix=".db"))
        pool = KnowledgeConnectionPool(db_path, max_connections=3)

        # Create a table first
        with pool.acquire() as conn:
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            conn.commit()

        results = []
        errors = []

        def worker(i):
            try:
                with pool.acquire() as conn:
                    conn.execute("INSERT INTO test (value) VALUES (?)", (f"thread_{i}",))
                    conn.commit()
                    results.append(i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent access errors: {errors}"
        assert len(results) == 10

        # Verify all rows were inserted
        with pool.acquire() as conn:
            count = conn.execute("SELECT COUNT(*) FROM test").fetchone()[0]
            assert count == 10

        pool.close_all()

    def test_pool_connection_reuse(self):
        """Connections should be reused from the pool."""
        from app.domain.knowledge.services.connection_pool import KnowledgeConnectionPool

        db_path = Path(tempfile.mktemp(suffix=".db"))
        pool = KnowledgeConnectionPool(db_path, max_connections=2)

        conn_ids = []

        for _ in range(5):
            with pool.acquire() as conn:
                conn_ids.append(id(conn))

        # Should reuse connections (not create 5 new ones)
        unique_ids = set(conn_ids)
        assert len(unique_ids) <= 2

        pool.close_all()


class TestFTSServiceWithPool:
    """Verify FTSService works with connection pool."""

    def test_fts_service_uses_pool(self):
        from app.domain.knowledge.services.search import FTSService
        from app.domain.knowledge.services.connection_pool import KnowledgeConnectionPool

        db_path = Path(tempfile.mktemp(suffix=".db"))
        pool = KnowledgeConnectionPool(db_path)
        fts = FTSService(pool=pool)

        assert fts.pool is pool
        pool.close_all()


class TestStoreConfigurability:
    """T-1.2: Verify storage path can be configured."""

    def test_store_custom_base_path(self):
        from app.domain.knowledge.services.store import KnowledgeStoreService

        with tempfile.TemporaryDirectory() as tmpdir:
            store = KnowledgeStoreService(base_path=tmpdir)
            assert store.base_path == Path(tmpdir)
            assert (store.base_path / "raw").exists()
            assert (store.base_path / "meta").exists()

    def test_store_default_path(self):
        from app.domain.knowledge.services.store import KnowledgeStoreService

        store = KnowledgeStoreService()
        assert "knowledge" in str(store.base_path)

    def test_singleton_respects_config(self):
        """get_store_service should use Settings.KNOWLEDGE_BASE_PATH."""
        from app.domain.knowledge.services.store import get_store_service

        # Reset singleton
        import app.domain.knowledge.services.store as store_module
        store_module._store_service = None

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.KNOWLEDGE_BASE_PATH = tmpdir
                store = get_store_service()
                assert str(store.base_path) == tmpdir


class TestBatchTagLoading:
    """T-1.3: Verify batch tag loading reduces N+1 queries."""

    def test_get_tags_batch_empty(self):
        from app.domain.knowledge.services.store import KnowledgeStoreService

        with tempfile.TemporaryDirectory() as tmpdir:
            store = KnowledgeStoreService(base_path=tmpdir)
            result = store.get_tags_batch([])
            assert result == {}

    def test_get_tags_batch_multiple_docs(self):
        """Batch load should fetch all tags in a single query."""
        import sqlite3
        from app.domain.knowledge.services.store import KnowledgeStoreService

        with tempfile.TemporaryDirectory() as tmpdir:
            store = KnowledgeStoreService(base_path=tmpdir)
            # Manually insert tags into search.db
            db_path = store.base_path / "search.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS doc_tags (doc_id TEXT, tag TEXT)")
                conn.executemany(
                    "INSERT INTO doc_tags (doc_id, tag) VALUES (?, ?)",
                    [
                        ("default/doc1.md", "auth"),
                        ("default/doc1.md", "api"),
                        ("default/doc2.md", "database"),
                        ("default/doc3.md", "auth"),
                    ]
                )
                conn.commit()

            tags = store.get_tags_batch(["default/doc1.md", "default/doc2.md", "default/doc3.md"])

            assert tags["default/doc1.md"] == ["auth", "api"]
            assert tags["default/doc2.md"] == ["database"]
            assert tags["default/doc3.md"] == ["auth"]


class TestMaintenanceReportPersistence:
    """T-1.4: Verify maintenance reports are persisted to SQLite."""

    def test_maintenance_reports_table_created(self):
        from app.domain.knowledge.services.search import FTSService
        from app.domain.knowledge.services.connection_pool import KnowledgeConnectionPool

        db_path = Path(tempfile.mktemp(suffix=".db"))
        pool = KnowledgeConnectionPool(db_path)
        fts = FTSService(pool=pool)

        # Initialize should create the table
        import asyncio
        asyncio.run(fts.initialize())

        with pool.acquire() as conn:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='maintenance_reports'"
            ).fetchone()
            assert result is not None
            assert result["name"] == "maintenance_reports"

        pool.close_all()

    def test_report_insert_and_query(self):
        from app.domain.knowledge.services.search import FTSService
        from app.domain.knowledge.services.connection_pool import KnowledgeConnectionPool

        db_path = Path(tempfile.mktemp(suffix=".db"))
        pool = KnowledgeConnectionPool(db_path)
        fts = FTSService(pool=pool)

        import asyncio
        asyncio.run(fts.initialize())

        # Insert a report
        with pool.acquire() as conn:
            conn.execute(
                """INSERT INTO maintenance_reports (level, dry_run, duration_seconds, summary_json)
                   VALUES (?, ?, ?, ?)""",
                ("medium", True, 12.5, '{"duplicates_found": 3}')
            )
            conn.commit()

        # Query it back
        with pool.acquire() as conn:
            row = conn.execute(
                "SELECT * FROM maintenance_reports ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
            assert row["level"] == "medium"
            assert row["dry_run"] == 1  # SQLite stores bool as int
            assert row["duration_seconds"] == 12.5
            assert "duplicates_found" in row["summary_json"]

        pool.close_all()
