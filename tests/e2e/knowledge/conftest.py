"""
E2E test fixtures for Knowledge Base HTTP API.

Creates a minimal FastAPI app with only the knowledge router,
using temporary directories and databases for isolation.
"""

import tempfile
from pathlib import Path
from typing import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Temp directories
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# E2E App & Client
# ---------------------------------------------------------------------------


@pytest.fixture
def e2e_app(
    temp_knowledge_dir: Path,
    temp_search_db: Path,
    temp_citations_db: Path,
) -> FastAPI:
    """
    Build a minimal FastAPI app with only the knowledge router,
    monkeypatched to use temporary storage.
    """
    import asyncio

    from app.api.routes import knowledge
    from app.domain.knowledge.services.bulk_import import BulkImportService
    from app.domain.knowledge.services.citations import CitationTracker
    from app.domain.knowledge.services.pipeline import IngestionPipeline
    from app.domain.knowledge.services.search import FTSService
    from app.domain.knowledge.services.store import KnowledgeStoreService

    # --- Monkeypatch module-level instances ---
    store = KnowledgeStoreService(base_path=str(temp_knowledge_dir))
    pipeline = IngestionPipeline(store=store)
    bulk_import = BulkImportService(pipeline)

    knowledge.store = store
    knowledge.pipeline = pipeline
    knowledge.bulk_import = bulk_import

    # --- Monkeypatch singleton getters to use temp DBs ---
    _fts_instance: FTSService | None = None
    _tracker_instance: CitationTracker | None = None

    def _get_fts_service(db_path=None):
        nonlocal _fts_instance
        if _fts_instance is None:
            _fts_instance = FTSService(db_path=temp_search_db)
        return _fts_instance

    def _get_citation_tracker(db_path=None):
        nonlocal _tracker_instance
        if _tracker_instance is None:
            _tracker_instance = CitationTracker(db_path=temp_citations_db)
        return _tracker_instance

    knowledge.get_fts_service = _get_fts_service
    knowledge.get_citation_tracker = _get_citation_tracker

    # --- Initialize databases and extractors ---
    async def _init():
        from app.domain.knowledge.extractors import ExtractorRegistry
        ExtractorRegistry.initialize_defaults()

        fts = _get_fts_service()
        await fts.initialize()
        tracker = _get_citation_tracker()
        await tracker.initialize()

    asyncio.run(_init())

    # Set module-level singletons so pipeline's direct imports resolve correctly
    import app.domain.knowledge.services.search as _search_mod
    import app.domain.knowledge.services.citations as _citations_mod

    _search_mod._fts_service = _fts_instance
    _citations_mod._tracker = _tracker_instance

    # --- Build minimal app ---
    app = FastAPI()
    app.include_router(knowledge.router, prefix="/api/v1/knowledge")
    return app


@pytest.fixture
def client(e2e_app: FastAPI) -> Generator[TestClient, None, None]:
    """Synchronous TestClient for the E2E app."""
    with TestClient(e2e_app) as c:
        yield c
