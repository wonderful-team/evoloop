"""
Shared fixtures for knowledge base integration tests.

Principles:
- No mocks (except LLM)
- Real SQLite, real file system, real LanceDB
- Isolated temp directories per test
"""

import asyncio
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest

from app.infrastructure.database.vector.lancedb_store import LanceVectorStore


# ---------------------------------------------------------------------------
# Fake Embedder (real implementation, not mock)
# ---------------------------------------------------------------------------

class FakeEmbedder:
    """Deterministic embedder for integration tests.

    Returns fixed-dimension vectors based on text hash.
    This is NOT a mock — it's a real embedder implementation
    that doesn't require external API calls.
    """

    DIM = 768

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        return [self._vectorize(d) for d in documents]

    async def embed_query(self, query: str) -> list[float]:
        return self._vectorize(query)

    def _vectorize(self, text: str) -> list[float]:
        """Deterministic pseudo-random vector from text."""
        import hashlib
        seed = int(hashlib.md5(text.encode()).hexdigest(), 16)
        import random
        rng = random.Random(seed)
        return [rng.random() for _ in range(self.DIM)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture(autouse=True)
def reset_lance_singleton() -> Generator[None, None, None]:
    """Reset LanceVectorStore singleton before each test."""
    LanceVectorStore._instance = None
    yield
    LanceVectorStore._instance = None


@pytest.fixture
def temp_knowledge_dir() -> Generator[Path, None, None]:
    """Temporary directory for knowledge base file storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_search_db() -> Generator[Path, None, None]:
    """Temporary SQLite database for FTS."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture
def temp_citations_db() -> Generator[Path, None, None]:
    """Temporary SQLite database for citations."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture
def temp_lancedb_dir() -> Generator[Path, None, None]:
    """Temporary directory for LanceDB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
