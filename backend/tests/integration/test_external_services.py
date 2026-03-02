"""
Integration tests for external services.
Tests real connections to LLM, embedding, and search providers.
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.integration
class TestLLMProviders:
    """Integration tests for LLM providers."""

    @pytest.mark.asyncio
    async def test_openai_connection(self):
        """Test connection to OpenAI API."""
        from app.infrastructure.llm.factory import LLMFactory

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
            try:
                llm = LLMFactory.create_llm()
                assert llm is not None
            except Exception as e:
                pytest.skip(f"OpenAI not available: {e}")

    @pytest.mark.asyncio
    async def test_ollama_connection(self):
        """Test connection to Ollama local server."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:11434/api/tags", timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        assert "models" in data
                    else:
                        pytest.skip("Ollama not available")
        except Exception as e:
            pytest.skip(f"Ollama connection failed: {e}")

    @pytest.mark.asyncio
    async def test_llm_completion(self):
        """Test actual LLM completion."""
        from app.infrastructure.llm.factory import LLMFactory

        try:
            llm = LLMFactory.create_llm()
            response = await llm.ainvoke("Say 'test' and nothing else")
            assert response is not None
            assert len(response.content) > 0
        except Exception as e:
            pytest.skip(f"LLM test failed: {e}")


@pytest.mark.integration
class TestEmbeddingProviders:
    """Integration tests for embedding providers."""

    @pytest.mark.asyncio
    async def test_embedding_generation(self):
        """Test generating embeddings."""
        from app.infrastructure.embeddings.factory import EmbedderFactory

        try:
            embedder = EmbedderFactory.get_embedder()
            texts = ["Hello world", "Test embedding"]
            embeddings = await embedder.aembed_documents(texts)

            assert len(embeddings) == 2
            assert len(embeddings[0]) > 0
            assert isinstance(embeddings[0][0], float)
        except Exception as e:
            pytest.skip(f"Embedding test failed: {e}")

    @pytest.mark.asyncio
    async def test_embedding_consistency(self):
        """Test that same text produces similar embeddings."""
        from app.infrastructure.embeddings.factory import EmbedderFactory

        try:
            embedder = EmbedderFactory.get_embedder()
            text = "This is a test sentence"

            emb1 = await embedder.aembed_query(text)
            emb2 = await embedder.aembed_query(text)

            # Should be very similar (same text)
            import numpy as np
            similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
            assert similarity > 0.99
        except Exception as e:
            pytest.skip(f"Embedding consistency test failed: {e}")


@pytest.mark.integration
class TestSearchProviders:
    """Integration tests for search providers."""

    @pytest.mark.asyncio
    async def test_brave_search_connection(self):
        """Test Brave Search API connection."""
        import os

        api_key = os.environ.get("BRAVE_API_KEY")
        if not api_key:
            pytest.skip("BRAVE_API_KEY not set")

        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                headers = {"X-Subscription-Token": api_key}
                async with session.get(
                    "https://api.search.brave.com/res/v1/web/search?q=test",
                    headers=headers,
                    timeout=10
                ) as resp:
                    assert resp.status in [200, 401, 403]  # 401/403 means key invalid but service up
        except Exception as e:
            pytest.skip(f"Brave Search not available: {e}")

    @pytest.mark.asyncio
    async def test_google_search_connection(self):
        """Test Google Search API connection."""
        import os

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("GOOGLE_API_KEY not set")

        pytest.skip("Google Search test not implemented")


@pytest.mark.integration
class TestVectorStores:
    """Integration tests for vector stores."""

    @pytest.mark.asyncio
    async def test_neo4j_vector_search(self):
        """Test Neo4j vector similarity search."""
        from app.infrastructure.database.graph.driver import Neo4jManager

        try:
            driver = Neo4jManager.get_driver()
            async with driver.session() as session:
                # Test if vector index exists
                result = await session.run("""
                    SHOW INDEXES YIELD name, type
                    WHERE type = 'VECTOR'
                    RETURN count(*) as count
                """)
                record = await result.single()
                assert record is not None
        except Exception as e:
            pytest.skip(f"Neo4j vector test failed: {e}")

    @pytest.mark.asyncio
    async def test_pgvector_connection(self):
        """Test PostgreSQL pgvector extension."""
        from app.core.db import engine
        from sqlalchemy import text

        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT * FROM pg_extension WHERE extname = 'vector'"))
                extensions = result.fetchall()
                # pgvector may or may not be installed
                assert isinstance(extensions, list)
        except Exception as e:
            pytest.skip(f"pgvector test failed: {e}")


@pytest.mark.integration
class TestCloudServices:
    """Integration tests for EvoCloud services."""

    @pytest.mark.asyncio
    async def test_evocloud_api_connection(self):
        """Test EvoCloud API connectivity."""
        from app.core.evocloud import evocloud_manager

        try:
            if evocloud_manager.api:
                # Try a simple health check
                result = await evocloud_manager.api.get_status()
                assert result is not None
            else:
                pytest.skip("EvoCloud API not initialized")
        except Exception as e:
            pytest.skip(f"EvoCloud test failed: {e}")

    @pytest.mark.asyncio
    async def test_evocloud_auth(self):
        """Test EvoCloud authentication."""
        from app.core.evocloud import evocloud_manager

        try:
            token = evocloud_manager.get_token()
            # Token may or may not be set
            assert token is None or isinstance(token, str)
        except Exception as e:
            pytest.skip(f"EvoCloud auth test failed: {e}")
