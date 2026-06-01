"""
Production Mode Integration Tests (Phase 6)

Validates that production-mode backend implementations (Redis, Meilisearch,
Neo4j, PostgreSQL) can initialize and perform basic operations.

These tests are SKIPPED automatically when the required external services are
not available. To run them, start the services via Docker Compose:

    docker-compose up -d neo4j redis meilisearch postgres
    pytest tests/integration/test_production_mode_integration.py --integration

Requirements:
- Redis on REDIS_URL (default: redis://localhost:6379/0)
- Meilisearch on MEILISEARCH_URL (default: http://localhost:7700)
- Neo4j on NEO4J_URI (default: bolt://localhost:7687)
- PostgreSQL on SQLALCHEMY_DATABASE_URI (default: postgresql+asyncpg://...)
"""

import asyncio
import socket
from unittest.mock import patch

import pytest

from app.core.config import settings


def _service_available(host: str, port: int) -> bool:
    """Check if a TCP service is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


# Skip conditions
NEO4J_AVAILABLE = _service_available("localhost", 7687)
REDIS_AVAILABLE = _service_available("localhost", 6379)
MEILISEARCH_AVAILABLE = _service_available("localhost", 7700)
POSTGRES_AVAILABLE = _service_available("localhost", 5432)

NEO4J_SKIP = pytest.mark.skipif(not NEO4J_AVAILABLE, reason="Neo4j not available (start with docker-compose up -d neo4j)")
REDIS_SKIP = pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis not available (start with docker-compose up -d redis)")
MEILISEARCH_SKIP = pytest.mark.skipif(not MEILISEARCH_AVAILABLE, reason="Meilisearch not available (start with docker-compose up -d meilisearch)")
POSTGRES_SKIP = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL not available (start with docker-compose up -d postgres)")


@pytest.fixture(autouse=True)
def production_settings(monkeypatch):
    """Force production mode for every test in this module."""
    monkeypatch.setenv("EMBEDDED_MODE", "false")
    yield


class TestRedisCache:
    """Production-mode cache integration with Redis."""

    @REDIS_SKIP
    def test_redis_set_get(self, production_settings):
        import app.infrastructure.cache as _cache_mod

        _cache_mod._cache_instance = None

        with patch.object(settings, "EMBEDDED_MODE", False):
            cache = _cache_mod.get_cache()

            async def _test():
                await cache.set("prod_test_key", "hello_redis")
                result = await cache.get("prod_test_key")
                assert result == "hello_redis"
                await cache.delete("prod_test_key")

            asyncio.run(_test())


class TestMeilisearchBackend:
    """Production-mode search integration with Meilisearch."""

    @MEILISEARCH_SKIP
    def test_meilisearch_index_and_search(self, production_settings):
        import app.infrastructure.search as _search_mod

        _search_mod._search_backend = None

        with patch.object(settings, "EMBEDDED_MODE", False):
            with patch.object(settings, "MEILISEARCH_URL", "http://localhost:7700"):
                with patch.object(settings, "MEILISEARCH_API_KEY", "evoloop-test-key"):
                    backend = _search_mod.get_search_backend()

                    async def _test():
                        from app.infrastructure.schemas import IndexDocumentRequest

                        doc = IndexDocumentRequest(
                            doc_id="prod_doc_1",
                            path="/prod/1",
                            title="Production Test",
                            content="Testing Meilisearch in production mode.",
                        )
                        success = await backend.index_document(doc)
                        assert success is True

                        # Meilisearch indexes asynchronously; wait a moment
                        import asyncio

                        await asyncio.sleep(0.5)

                        results = await backend.search("Meilisearch", limit=5)
                        assert results.total >= 1

                    asyncio.run(_test())


class TestNeo4jGraphDriver:
    """Production-mode graph integration with Neo4j."""

    @NEO4J_SKIP
    def test_neo4j_create_and_query(self, production_settings):
        from app.infrastructure.database.graph.driver import GraphManager
        from app.infrastructure.database.graph.neo4j import Neo4jDriver

        # Force Neo4j driver (class attr is set at import time based on EMBEDDED_MODE)
        GraphManager._use_neo4j = True

        async def _test():
            driver = Neo4jDriver(
                uri=settings.NEO4J_URI or "bolt://localhost:7687",
                user=settings.NEO4J_USER or "neo4j",
                password=settings.NEO4J_PASSWORD or "admin888",
            )
            try:
                await driver.execute_query(
                    "CREATE (n:TestNode {name: $name}) RETURN n",
                    {"name": "ProductionTest"},
                )
                result = await driver.execute_query(
                    "MATCH (n:TestNode {name: $name}) RETURN n.name",
                    {"name": "ProductionTest"},
                )
                assert len(result) == 1
                assert result[0]["n.name"] == "ProductionTest"
                await driver.execute_query(
                    "MATCH (n:TestNode {name: $name}) DELETE n",
                    {"name": "ProductionTest"},
                )
            finally:
                await driver.close()

        asyncio.run(_test())


class TestPostgresVectorStore:
    """Production-mode vector storage integration with PostgreSQL + pgvector."""

    @POSTGRES_SKIP
    def test_pgvector_upsert_and_search(self, production_settings):
        from app.infrastructure.database.vector import get_vector_store

        store = get_vector_store()
        vec = [0.1] * settings.EMBEDDING_DIMENSIONS
        chunks = [
            {
                "file_path": "prod.py",
                "content": "def prod(): pass",
                "start_line": 1,
                "end_line": 2,
                "identifier": "prod",
                "repository_id": "repo_prod",
                "chunk_type": "function",
                "language": "python",
            }
        ]
        store.upsert_code_chunks(chunks, [vec])
        results = store.search_code(vec, repository_id="repo_prod", top_k=5)
        assert len(results) == 1
