import os
import pytest
import asyncio
from unittest.mock import patch, MagicMock

# Force embedded mode for testing
os.environ["EMBEDDED_MODE"] = "true"

from app.infrastructure.embeddings.factory import EmbedderFactory
from app.infrastructure.embeddings.local import LocalEmbedder
from app.infrastructure.database.vector import get_vector_store
from app.infrastructure.database.vector.lancedb_store import LanceVectorStore
from app.infrastructure.queue.factory import get_scheduler
from app.infrastructure.queue.huey_queue import HueyTaskScheduler
from app.infrastructure.queue.celery import LocalCelery
from app.infrastructure.database.resource_manager import db_resource_manager

@pytest.mark.asyncio
async def test_embedder_factory_fallback():
    """Verify that EmbedderFactory falls back to LocalEmbedder when no provider is configured."""
    # Ensure no provider is configured in environment (already handled by os.environ above if it was clean)
    with patch("app.infrastructure.config.SystemConfigService.get_value", return_value=None):
        embedder = EmbedderFactory.get_embedder()
        assert isinstance(embedder, LocalEmbedder)
        print("\n✅ EmbedderFactory correctly fell back to LocalEmbedder")

@pytest.mark.asyncio
async def test_vector_store_functional():
    """Verify that get_vector_store returns a functional LanceVectorStore in embedded mode."""
    store = get_vector_store()
    assert isinstance(store, LanceVectorStore)
    # Check that it's not a NoOp (it should have real methods)
    assert hasattr(store, "upsert_code_chunks")
    assert hasattr(store, "search_code")
    print("✅ VectorStore resolved to functional LanceVectorStore")

@pytest.mark.asyncio
async def test_scheduler_functional():
    """Verify that get_scheduler returns a functional scheduler, not a NoOp."""
    scheduler = get_scheduler()
    # In embedded mode, it should be Huey or LocalCelery
    assert isinstance(scheduler, (HueyTaskScheduler, LocalCelery))
    assert hasattr(scheduler, "task")
    assert hasattr(scheduler, "send_task")
    print(f"✅ Scheduler resolved to functional {type(scheduler).__name__}")

@pytest.mark.asyncio
async def test_db_resource_manager_functional():
    """Verify that db_resource_manager is initialized and functional."""
    # We don't want to actually initialize and touch the disk too much in a unit test,
    # but we can check its state.
    from app.infrastructure.database.resource_manager import DatabaseResourceManager
    assert isinstance(db_resource_manager, DatabaseResourceManager)
    await db_resource_manager.initialize(create_tables=True)
    assert db_resource_manager.checkpointer is not None
    print("✅ DatabaseResourceManager initialized and has functional checkpointer")

if __name__ == "__main__":
    # Manual run support
    async def run_all():
        await test_embedder_factory_fallback()
        await test_vector_store_functional()
        await test_scheduler_functional()
        await test_db_resource_manager_functional()
        print("\n✨ All Infrastructure Sanitization Regression Tests PASSED ✨")

    asyncio.run(run_all())
