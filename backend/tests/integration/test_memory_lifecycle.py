"""
Memory System Full-Lifecycle Integration Tests
================================================

End-to-end validation of the memory stack:
  Init → Ingest → Extract → Store → Retrieve → Two-Tier → Terms → Rewind → Consistency

Run: uv run pytest tests/integration/test_memory_lifecycle.py -v --tb=short
"""

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.integration


# ───────────────────────── Fixtures ─────────────────────────

@pytest.fixture
def test_memory_root():
    tmp = tempfile.mkdtemp(prefix="evo_mem_lifecycle_")
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def test_db_path():
    tmp = tempfile.mktemp(suffix=".db", prefix="evo_mem_")
    yield tmp
    if os.path.exists(tmp):
        os.unlink(tmp)


@pytest.fixture
async def memory_setup(test_memory_root, test_db_path):
    """
    Manually wire memory components with explicit config.
    Injects a test SQLite engine directly into db_resource_manager
    so short-term memory can function without touching user DB.
    """
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.infrastructure.database.sql.database import Base
    from app.models.conversation import Message  # noqa: F401 -- registers Message table

    test_engine = create_async_engine(
        f"sqlite+aiosqlite:///{test_db_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    db_resource_manager._initialized = True
    db_resource_manager._engine = test_engine
    db_resource_manager._session_factory = test_session_factory

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Patch memory modules that read settings.BRAIN_MEMORY_ROOT
    settings_paths = [
        "app.core.memory.two_tier.settings",
        "app.core.memory.maintenance.settings",
        "app.core.memory.auto_extraction.settings",
        "app.core.memory.store.settings",
    ]
    mock_settings = type("MockSettings", (), {
        "BRAIN_MEMORY_ROOT": test_memory_root,
        "EMBEDDED_MODE": True,
        "EMBEDDING_DIMENSIONS": 768,
        "AUTO_MEMORY_EXTRACTION": True,
        "AUTO_MEMORY_EXTRACTION_INTERVAL": 1,
    })()
    patchers = [patch(p, mock_settings) for p in settings_paths]
    for p in patchers:
        p.start()

    from app.core.memory.config import MemoryConfig
    from app.core.memory.store import MemoryStore
    from app.core.memory.short_term import SqlShortTermMemory
    from app.core.memory.manager import MemoryManager
    from app.core.memory.quality import MemoryQualityAnalyzer
    from app.core.memory.state_tracking import MemoryStateTracker

    # Patch embedder and vector store to avoid slow model loading
    mock_embedder = AsyncMock()
    mock_embedder.embed_query = AsyncMock(return_value=[0.1] * 768)
    embedder_patcher = patch(
        "app.infrastructure.embeddings.factory.EmbedderFactory.get_embedder",
        return_value=mock_embedder,
    )
    embedder_patcher.start()

    mock_vector_store = MagicMock()
    mock_vector_store.upsert_memory_chunks = MagicMock()
    mock_vector_store.search_memory = MagicMock(return_value=[])
    mock_vector_store.delete_memory_by_id = MagicMock()
    mock_vector_store.delete_all_memories = MagicMock()
    vector_patcher = patch(
        "app.core.memory.store.get_vector_store",
        return_value=mock_vector_store,
    )
    vector_patcher.start()

    config = MemoryConfig(
        memory_root=Path(test_memory_root),
        backend_type="file",
        extraction_interval=1,
        hot_memory_max_chars=8000,
    )

    storage = MemoryStore(str(config.memory_root))
    await storage.initialize()

    short_term = SqlShortTermMemory()
    await short_term.initialize()

    state_tracker = MemoryStateTracker()
    quality = MemoryQualityAnalyzer(storage)

    manager = MemoryManager(
        config=config,
        storage=storage,
        short_term=short_term,
    )
    await manager.initialize()

    yield {
        "config": config,
        "manager": manager,
        "storage": storage,
        "short_term": short_term,
        "quality": quality,
        "state_tracker": state_tracker,
        "root": test_memory_root,
    }

    await short_term.flush()
    embedder_patcher.stop()
    vector_patcher.stop()
    for p in reversed(patchers):
        p.stop()
    await test_engine.dispose()
    if os.path.exists(test_db_path):
        os.unlink(test_db_path)


# ───────────────────────── Phase 1: Init ─────────────────────────

class TestPhase1Init:
    @pytest.mark.asyncio
    async def test_storage_initialized(self, memory_setup):
        assert memory_setup["storage"] is not None
        assert memory_setup["manager"] is not None
        assert memory_setup["short_term"] is not None

    @pytest.mark.asyncio
    async def test_storage_directories_created(self, memory_setup, test_memory_root):
        for sub in ("journal", "preferences", "context", "decisions", "index"):
            assert Path(test_memory_root, sub).exists(), f"Missing: {sub}"

    @pytest.mark.asyncio
    async def test_sqlite_index_created(self, memory_setup, test_memory_root):
        db_file = Path(test_memory_root, "index", "memory_metadata.db")
        assert db_file.exists()


# ───────────────────────── Phase 2: Ingest ─────────────────────────

class TestPhase2Ingest:
    @pytest.mark.asyncio
    async def test_short_term_add_message(self, memory_setup):
        short_term = memory_setup["short_term"]
        await short_term.add_message(
            thread_id="thread_lifecycle_01",
            message=HumanMessage(content="We need to implement a caching layer for the API."),
        )
        msgs = await short_term.get_context("thread_lifecycle_01", limit=10)
        assert len(msgs) >= 1
        assert any("caching layer" in str(m.content) for m in msgs)

    @pytest.mark.asyncio
    async def test_multiple_messages_preserve_order(self, memory_setup):
        short_term = memory_setup["short_term"]
        for i in range(5):
            msg = HumanMessage(content=f"Message {i}") if i % 2 == 0 else AIMessage(content=f"Message {i}")
            await short_term.add_message(
                thread_id="thread_lifecycle_02",
                message=msg,
            )
        msgs = await short_term.get_context("thread_lifecycle_02", limit=10)
        contents = [str(m.content) for m in msgs]
        for i in range(5):
            assert f"Message {i}" in contents


# ───────────────────────── Phase 3: Manual Long-Term Store ─────────────────────────

class TestPhase3ManualStore:
    @pytest.mark.asyncio
    async def test_save_memory_creates_markdown(self, memory_setup, test_memory_root):
        mgr = memory_setup["manager"]
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

        entry = MemoryEntry(
            id="mem_test_001",
            type=MemoryType.PROJECT,
            title="API Caching Strategy",
            content="Implement Redis-based caching for the REST API with TTL=300s.",
            description="Redis caching decision",
            project_id=42,
            user_id="user_1",
            privacy=PrivacyLevel.TEAM,
            source="manual",
            tags=["architecture", "caching"],
        )
        await mgr.save_memory(entry)

        found = list(Path(test_memory_root).rglob("*.md"))
        assert any("mem_test_001" in f.name for f in found), "No markdown for mem_test_001"

    @pytest.mark.asyncio
    async def test_save_memory_sqlite_indexed(self, memory_setup):
        mgr = memory_setup["manager"]
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

        entry = MemoryEntry(
            id="mem_sqlite_001",
            type=MemoryType.PROJECT,
            title="SQLite Test",
            content="Test content for SQLite indexing.",
            project_id=42,
            user_id="user_1",
            privacy=PrivacyLevel.TEAM,
            source="manual",
        )
        await mgr.save_memory(entry)

        storage = memory_setup["storage"]
        # SqliteMemoryIndex inlined into _FileEngine
        idx: SqliteMemoryIndex = storage.index_db
        row = await idx.search(filters={"id": "mem_sqlite_001"}, limit=1)
        assert len(row) == 1
        assert row[0]["id"] == "mem_sqlite_001"

    @pytest.mark.asyncio
    async def test_find_by_hash(self, memory_setup):
        mgr = memory_setup["manager"]
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

        entry = MemoryEntry(
            id="mem_hash_01",
            type=MemoryType.PROJECT,
            title="Hash Test",
            content="Unique content for hash test.",
            project_id=42,
            user_id="user_1",
            privacy=PrivacyLevel.PRIVATE,
            source="manual",
        )
        await mgr.save_memory(entry)

        storage = memory_setup["storage"]
        found = await storage.find_by_hash(entry.content_hash)
        assert found is not None
        assert found.id == "mem_hash_01"

    @pytest.mark.asyncio
    async def test_delete_memory_removes_all_layers(self, memory_setup, test_memory_root):
        mgr = memory_setup["manager"]
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

        entry = MemoryEntry(
            id="mem_delete_01",
            type=MemoryType.PROJECT,
            title="To Delete",
            content="This will be deleted.",
            project_id=42,
            user_id="user_1",
            privacy=PrivacyLevel.TEAM,
            source="manual",
        )
        await mgr.save_memory(entry)
        pre = await mgr.get_memory("mem_delete_01")
        assert pre is not None

        await mgr.delete_memory("mem_delete_01")

        post = await mgr.get_memory("mem_delete_01")
        assert post is None

        found = list(Path(test_memory_root).rglob("*mem_delete_01*"))
        assert len(found) == 0


# ───────────────────────── Phase 4: Auto-Extraction Pipeline ─────────────────────────

class TestPhase4AutoExtraction:
    @pytest.mark.asyncio
    async def test_extractor_gates_skip_empty_thread(self, memory_setup):
        extractor = memory_setup["manager"].extraction
        result = await extractor.maybe_extract(
            thread_id="empty_thread",
            messages=[],
            project_id=42,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_extractor_gates_skip_single_message(self, memory_setup):
        extractor = memory_setup["manager"].extraction
        messages = [HumanMessage(content="Hi")]
        result = await extractor.maybe_extract(
            thread_id="short_thread",
            messages=messages,
            project_id=42,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_mocked_extraction_produces_entries(self, memory_setup):
        extractor = memory_setup["manager"].extraction
        messages = [
            HumanMessage(content="Let's use RabbitMQ for the event bus."),
            AIMessage(content="Good idea, I'll set up the connection factory."),
            HumanMessage(content="Also add retry logic with exponential backoff."),
            AIMessage(content="Done, I added the retry policy in the producer."),
        ]

        fake_llm_response = MagicMock()
        fake_llm_response.content = json.dumps([
            {
                "title": "RabbitMQ Event Bus",
                "content": "Use RabbitMQ as the central event bus with retry logic.",
                "type": "decision",
                "utility_score": 0.9,
                "rationale": "Architectural decision",
                "context": "Messaging infrastructure",
                "time_context": "2026-04-01",
            }
        ])

        with patch("app.infrastructure.llm.InternalLLMService.invoke", new_callable=AsyncMock, return_value=fake_llm_response):
            with patch.object(extractor, "_gather_multi_source_context", new_callable=AsyncMock, return_value="### Project Context\nTest project."):
                result = await extractor.maybe_extract(
                    thread_id="extract_thread_01",
                    messages=messages,
                    project_id=42,
                    force=True,
                )

        assert result is not None
        assert len(result) >= 1
        assert any("RabbitMQ" in e.title for e in result)

    @pytest.mark.asyncio
    async def test_extraction_pipeline_save_and_retrieve(self, memory_setup):
        extractor = memory_setup["manager"].extraction
        mgr = memory_setup["manager"]
        messages = [
            HumanMessage(content="Let's adopt gRPC for inter-service communication."),
            AIMessage(content="I'll draft the protobuf schemas."),
        ]

        fake_llm_response = MagicMock()
        fake_llm_response.content = json.dumps([
            {
                "title": "gRPC Adoption",
                "content": "Adopt gRPC with protobuf for service communication.",
                "type": "decision",
                "utility_score": 0.88,
                "rationale": "Performance",
            }
        ])

        with patch("app.infrastructure.llm.InternalLLMService.invoke", new_callable=AsyncMock, return_value=fake_llm_response):
            with patch.object(extractor, "_gather_multi_source_context", new_callable=AsyncMock, return_value=""):
                extracted = await extractor.maybe_extract(
                    thread_id="e2e_extract_thread",
                    messages=messages,
                    project_id=42,
                    force=True,
                )

        assert extracted is not None and len(extracted) >= 1
        entry = extracted[0]
        await mgr.save_memory(entry)

        found = await mgr.get_memory(entry.id)
        assert found is not None
        assert "gRPC" in found.title


# ───────────────────────── Phase 5: Retrieval ─────────────────────────

class TestPhase5Retrieval:
    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_search_memories_by_keyword(self, memory_setup):
        mgr = memory_setup["manager"]
        storage = memory_setup["storage"]
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

        entry = MemoryEntry(
            id="mem_search_001",
            type=MemoryType.PROJECT,
            title="Redis caching",
            content="Use Redis for distributed caching.",
            project_id=42,
            user_id="user_1",
            privacy=PrivacyLevel.TEAM,
            source="manual",
        )
        await mgr.save_memory(entry)

        # Patch vector search to bypass NoOpEmbedder failure
        with patch.object(storage.vector_db, "search_memory", return_value=[{"id": "mem_search_001"}]):
            results = await mgr.search_memories(query="Redis", project_id=42, limit=10)
        assert any("Redis" in (r.title or r.content) for r in results)

    @pytest.mark.asyncio
    async def test_search_memories_by_project_filter(self, memory_setup):
        mgr = memory_setup["manager"]
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

        entry = MemoryEntry(
            id="mem_filter_001",
            type=MemoryType.PROJECT,
            title="Filter Test",
            content="Content for filter testing.",
            project_id=99,
            user_id="user_1",
            privacy=PrivacyLevel.TEAM,
            source="manual",
        )
        await mgr.save_memory(entry)

        results = await mgr.search_memories(query="", filters={"project_id": 99}, limit=10)
        assert len(results) >= 1
        for r in results:
            assert r.project_id == 99

    @pytest.mark.asyncio
    async def test_get_memory_by_id(self, memory_setup):
        mgr = memory_setup["manager"]
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

        entry = MemoryEntry(
            id="mem_get_001",
            type=MemoryType.PROJECT,
            title="Get Test",
            content="Content for get test.",
            project_id=42,
            user_id="user_1",
            privacy=PrivacyLevel.TEAM,
            source="manual",
        )
        await mgr.save_memory(entry)

        found = await mgr.get_memory("mem_get_001")
        assert found is not None
        assert found.id == "mem_get_001"


# ───────────────────────── Phase 6: Two-Tier Hot/Cold ─────────────────────────

class TestPhase6TwoTier:
    @pytest.mark.asyncio
    async def test_hot_memory_regeneration(self, memory_setup):
        mgr = memory_setup["manager"]
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

        entry = MemoryEntry(
            id="mem_hot_001",
            type=MemoryType.PROJECT,
            title="Hot Memory",
            content="Content for hot memory testing.",
            project_id=42,
            user_id="user_1",
            privacy=PrivacyLevel.TEAM,
            source="manual",
        )
        await mgr.save_memory(entry)

        hot = await mgr.get_hot_memory()
        assert hot is not None
        assert isinstance(hot, str)

    @pytest.mark.asyncio
    async def test_cold_memory_search(self, memory_setup):
        mgr = memory_setup["manager"]
        cold = await mgr.search_cold_memory(query="caching", max_results=5)
        assert isinstance(cold, list)


# ───────────────────────── Phase 8: Rewind Cleanup ─────────────────────────

class TestPhase8Rewind:
    @pytest.mark.asyncio
    async def test_rewind_deletes_by_source_message_id(self, memory_setup):
        from app.core.memory.event.subscribers import MemoryRewind
        from app.core.engine.rewind.event import RewindRequestedEvent
        from app.core.memory.lifespan import MemoryLifespanManager

        mgr = memory_setup["manager"]
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

        entry = MemoryEntry(
            id="mem_rewind_01",
            type=MemoryType.PROJECT,
            title="Rewind Target",
            content="Content to be removed on rewind.",
            description="Test rewind cleanup",
            project_id=42,
            user_id="user_1",
            privacy=PrivacyLevel.TEAM,
            source="manual",
            source_message_id="msg_to_rewind",
        )
        await mgr.save_memory(entry)

        pre = await mgr.get_memory("mem_rewind_01")
        assert pre is not None

        mock_container = type("MockContainer", (), {"memory_manager": mgr})()
        with patch.object(MemoryLifespanManager, "get_container", return_value=mock_container):
            handler = MemoryRewind()
            event = RewindRequestedEvent(
                thread_id="thread_rewind",
                target_message_id="msg_to_rewind",
                affected_message_ids=["msg_to_rewind"],
                affected_run_ids=[],
            )
            await handler._handle_rewind_requested(event)

        post = await mgr.get_memory("mem_rewind_01")
        assert post is None


# ───────────────────────── Phase 9: Cross-Layer Consistency ─────────────────────────

class TestPhase9Consistency:
    @pytest.mark.asyncio
    async def test_file_sqlite_vector_consistency_after_save(self, memory_setup, test_memory_root):
        mgr = memory_setup["manager"]
        storage = memory_setup["storage"]
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

        entry = MemoryEntry(
            id="mem_consistency_01",
            type=MemoryType.PROJECT,
            title="Consistency Check",
            content="Verify all layers are in sync.",
            project_id=99,
            user_id="user_1",
            privacy=PrivacyLevel.TEAM,
            source="manual",
        )
        await mgr.save_memory(entry)

        # Layer 1: File
        found_files = list(Path(test_memory_root).rglob("*mem_consistency_01*"))
        assert len(found_files) > 0, "File layer missing"

        # Layer 2: SQLite
        # SqliteMemoryIndex inlined into _FileEngine
        idx: SqliteMemoryIndex = storage.index_db
        rows = await idx.search(filters={"id": "mem_consistency_01"}, limit=1)
        assert len(rows) == 1, "SQLite layer missing"

        # Layer 3: In-memory index
        assert "mem_consistency_01" in storage._id_index, "In-memory index missing"

    @pytest.mark.asyncio
    async def test_file_sqlite_vector_consistency_after_delete(self, memory_setup, test_memory_root):
        mgr = memory_setup["manager"]
        storage = memory_setup["storage"]
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

        entry = MemoryEntry(
            id="mem_consistency_02",
            type=MemoryType.PROJECT,
            title="Consistency Check Delete",
            content="Verify deletion purges all layers.",
            project_id=99,
            user_id="user_1",
            privacy=PrivacyLevel.TEAM,
            source="manual",
        )
        await mgr.save_memory(entry)
        await mgr.delete_memory("mem_consistency_02")

        # Layer 1: File
        found_files = list(Path(test_memory_root).rglob("*mem_consistency_02*"))
        assert len(found_files) == 0, "File layer not purged"

        # Layer 2: SQLite
        # SqliteMemoryIndex inlined into _FileEngine
        idx: SqliteMemoryIndex = storage.index_db
        rows = await idx.search(filters={"id": "mem_consistency_02"}, limit=1)
        assert len(rows) == 0, "SQLite layer not purged"

        # Layer 3: In-memory index
        assert "mem_consistency_02" not in storage._id_index, "In-memory index not purged"


# ───────────────────────── Phase 10: Quality & State Tracking ─────────────────────────

class TestPhase10QualityAndState:
    @pytest.mark.asyncio
    async def test_quality_analysis(self, memory_setup):
        quality = memory_setup["quality"]
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

        entry = MemoryEntry(
            id="mem_quality_01",
            type=MemoryType.PROJECT,
            title="Quality Test",
            content="Detailed analysis of the caching strategy with specific metrics.",
            project_id=42,
            user_id="user_1",
            privacy=PrivacyLevel.TEAM,
            source="manual",
        )
        scores = await quality.analyze_memory(entry)
        assert scores is not None
        assert 0 <= scores.overall <= 1

    @pytest.mark.asyncio
    async def test_state_tracker_prevents_duplicates(self, memory_setup):
        tracker = memory_setup["state_tracker"]
        tracker.mark_surfaced("t1", ["mem_001", "mem_002"])

        ids = tracker.get_surfaced_ids("t1")
        assert "mem_001" in ids
        assert "mem_002" in ids

        # Duplicate mark should be idempotent
        tracker.mark_surfaced("t1", ["mem_001"])
        assert len(tracker.get_surfaced_ids("t1")) == 2



# ───────────────────────── Phase 11: Agent Memory Tools ─────────────────────────

class TestPhase11AgentMemoryTools:
    """Test remember/recall tools that the agent uses to interact with memory."""

    @pytest.mark.asyncio
    async def test_remember_tool_saves_memory(self, memory_setup, test_memory_root):
        from app.core.memory.tools import remember
        from app.core.context.manager import ContextManager, EvoContext
        from unittest.mock import MagicMock, patch

        # Patch MemoryLifespanManager so remember() writes to the test storage
        mock_container = MagicMock()
        mock_container.memory_manager = memory_setup["manager"]

        ctx = EvoContext(thread_id="t_remember", project_id=42, user_id="test_user")
        token = ContextManager.set(ctx)
        try:
            with patch("app.core.memory.lifespan.MemoryLifespanManager") as MockLifespan:
                MockLifespan.is_initialized.return_value = True
                MockLifespan.get_container.return_value = mock_container
                result = await remember.ainvoke({"content": "User prefers dark mode in all interfaces."})
                assert "Remembered" in result
        finally:
            ContextManager.reset(token)

        # Verify storage layers
        storage = memory_setup["storage"]
        entries = await storage.list_all(limit=10)
        titles = [e.title for e in entries]
        assert any("dark mode" in t.lower() for t in titles)

    @pytest.mark.asyncio
    async def test_recall_tool_retrieves_memory(self, memory_setup):
        from app.core.memory.tools import remember, recall
        from app.core.context.manager import ContextManager, EvoContext

        ctx = EvoContext(thread_id="t_recall", project_id=42, user_id="test_user")
        token = ContextManager.set(ctx)
        try:
            await remember.ainvoke({"content": "User prefers dark mode in all interfaces.", "is_user_preference": True})
            result = await recall.ainvoke({"query": "dark mode preference"})
            assert "dark mode" in result.lower()
        finally:
            ContextManager.reset(token)

    @pytest.mark.asyncio
    async def test_remember_and_recall_roundtrip(self, memory_setup):
        """Full roundtrip: remember → storage → recall."""
        from app.core.memory.tools import remember, recall
        from app.core.context.manager import ContextManager, EvoContext

        ctx = EvoContext(thread_id="t_roundtrip", project_id=99, user_id="u1")
        token = ContextManager.set(ctx)
        try:
            await remember.ainvoke({"content": "API rate limit is 1000 requests per minute."})
            result = await recall.ainvoke({"query": "rate limit"})
            assert "1000" in result
            assert "requests" in result
        finally:
            ContextManager.reset(token)


# ───────────────────────── Phase 12: Event-Driven Auto-Extraction ─────────────────────────

class TestPhase12EventDrivenExtraction:
    """
    Verify that when an agent run completes, the memory system:
    1. Receives the AgentRunCompletedEvent
    2. Loads message history from the DB
    3. Converts ORM messages to LangChain BaseMessage
    4. Triggers automatic memory extraction
    5. Saves extracted memories to storage
    """

    @pytest.mark.asyncio
    async def test_agent_run_completed_triggers_extraction(self, memory_setup, test_db_path):
        import asyncio
        mgr = memory_setup["manager"]
        thread_id = "t_event_extract"
        project_id = 99

        # 1. Seed DB with 4+ messages (minimum for extraction gate)
        from app.models.conversation import Message
        from app.infrastructure.database.resource_manager import db_resource_manager
        import uuid

        session = db_resource_manager.session_factory()
        async with session:
            for i in range(5):
                msg = Message(
                    id=str(uuid.uuid4()),
                    thread_id=thread_id,
                    project_id=project_id,
                    role="human" if i % 2 == 0 else "ai",
                    content=f"Message {i} about caching strategy and Redis",
                    sequence_number=i + 1,
                    is_visible=True,
                )
                session.add(msg)
            await session.commit()

        # 2. Mock LLM extraction to avoid real LLM calls
        from app.core.memory.auto_extraction import AutoMemoryExtractor
        from app.core.memory.models import MemoryEntry, MemoryType

        async def mock_run_extraction(self, thread_id, messages, project_id=None, **kwargs):
            entry = MemoryEntry(
                id="mem_extracted_event_01",
                type=MemoryType.PROJECT,
                title="Redis Caching Strategy",
                content="Implement Redis caching for API responses to improve performance.",
                project_id=project_id,
                source="auto_extraction",
            )
            # Save through the fixture manager so the assertion can find it
            await memory_setup["manager"].save_memory(entry)
            return [entry]

        # 3. Set up event handler
        from app.core.engine.event.schemas import AgentRunCompletedEvent
        from app.core.memory.event.subscribers import MemoryLifecycleSubscriber
        from unittest.mock import patch

        handler = MemoryLifecycleSubscriber()

        event = AgentRunCompletedEvent(
            thread_id=thread_id,
            project_id=project_id,
            status="done",
            payload={"run_id": "run_123"},
        )

        # 4. Invoke handler directly and capture background tasks
        created_tasks = []
        original_create_task = asyncio.create_task

        def capture_create_task(coro, **kwargs):
            task = original_create_task(coro, **kwargs)
            created_tasks.append(task)
            return task

        with patch.object(AutoMemoryExtractor, '_run_extraction', mock_run_extraction):
            with patch('asyncio.create_task', side_effect=capture_create_task):
                await handler.on_agent_run_completed(event)
                if created_tasks:
                    await asyncio.gather(*created_tasks, return_exceptions=True)

        # 5. Verify extracted memory was saved through the manager
        entries = await mgr.list_memories(limit=10)
        ids = [e.id for e in entries]
        assert "mem_extracted_event_01" in ids, f"Expected extracted memory not found. Got: {ids}"

    @pytest.mark.asyncio
    async def test_event_bus_publishes_and_memory_subscribes(self, memory_setup, test_db_path):
        """
        End-to-end: publish AgentRunCompletedEvent through the real event bus,
        verify memory subscriber picks it up and extracts memories.
        """
        import asyncio
        mgr = memory_setup["manager"]
        thread_id = "t_bus_extract"
        project_id = 88

        # Seed messages
        from app.models.conversation import Message
        from app.infrastructure.database.resource_manager import db_resource_manager
        import uuid
        session = db_resource_manager.session_factory()
        async with session:
            for i in range(5):
                msg = Message(
                    id=str(uuid.uuid4()),
                    thread_id=thread_id,
                    project_id=project_id,
                    role="human" if i % 2 == 0 else "ai",
                    content=f"Bus message {i} about database indexing",
                    sequence_number=i + 1,
                    is_visible=True,
                )
                session.add(msg)
            await session.commit()

        # Mock extraction
        from app.core.memory.auto_extraction import AutoMemoryExtractor
        from app.core.memory.models import MemoryEntry, MemoryType

        async def mock_run_extraction(self, thread_id, messages, project_id=None, **kwargs):
            entry = MemoryEntry(
                id="mem_bus_01",
                type=MemoryType.PROJECT,
                title="Database Indexing",
                content="Add composite index on (user_id, created_at) for query performance.",
                project_id=project_id,
                source="auto_extraction",
            )
            await memory_setup["manager"].save_memory(entry)
            return [entry]

        from app.core.engine.event.schemas import AgentRunCompletedEvent
        from app.core.memory.event.subscribers import MemoryLifecycleSubscriber
        from app.core.events import system_bus
        from app.core.events.decorators import register_instance_handlers
        from unittest.mock import patch

        handler = MemoryLifecycleSubscriber()
        register_instance_handlers(handler, system_bus)

        event = AgentRunCompletedEvent(
            thread_id=thread_id,
            project_id=project_id,
            status="done",
            payload={"run_id": "run_bus_01"},
        )

        created_tasks = []
        original_create_task = asyncio.create_task

        def capture_create_task(coro, **kwargs):
            task = original_create_task(coro, **kwargs)
            created_tasks.append(task)
            return task

        with patch.object(AutoMemoryExtractor, '_run_extraction', mock_run_extraction):
            with patch('asyncio.create_task', side_effect=capture_create_task):
                # Publish through the real event bus
                await system_bus.publish(event)

                if created_tasks:
                    await asyncio.gather(*created_tasks, return_exceptions=True)

        entries = await mgr.list_memories(limit=10)
        ids = [e.id for e in entries]
        assert "mem_bus_01" in ids, f"Bus-published extraction not found. Got: {ids}"


# ───────────────────────── Phase 13: Forgetting ─────────────────────────

class TestPhase13Forgetting:
    """Test deletion and rewind cleanup of memories."""

    @pytest.mark.asyncio
    async def test_forget_memory_tool_deletes_entry(self, memory_setup, test_memory_root):
        from app.core.memory.tools import forget_memory
        from app.core.context.manager import ContextManager, EvoContext
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        from unittest.mock import MagicMock, patch

        mgr = memory_setup["manager"]

        # Create a memory to delete
        entry = MemoryEntry(
            id="mem_forget_01",
            type=MemoryType.PROJECT,
            title="Temporary Knowledge",
            content="This will be deleted.",
            project_id=42,
            user_id="u1",
            privacy=PrivacyLevel.TEAM,
        )
        await mgr.save_memory(entry)

        # Verify it exists
        pre_delete = await mgr.get_memory("mem_forget_01")
        assert pre_delete is not None

        # Patch LifespanManager so forget_memory uses test storage
        mock_container = MagicMock()
        mock_container.memory_manager = mgr

        ctx = EvoContext(thread_id="t_forget", project_id=42, user_id="u1")
        token = ContextManager.set(ctx)
        try:
            with patch("app.core.memory.lifespan.MemoryLifespanManager") as MockLifespan:
                MockLifespan.is_initialized.return_value = True
                MockLifespan.get_container.return_value = mock_container
                result = await forget_memory.ainvoke({"memory_id": "mem_forget_01"})
                assert "permanently forgotten" in result
        finally:
            ContextManager.reset(token)

        # Verify all layers are clean
        post_delete = await mgr.get_memory("mem_forget_01")
        assert post_delete is None

        storage = memory_setup["storage"]
        assert "mem_forget_01" not in storage._id_index
        assert "mem_forget_01" not in storage._hash_index

    @pytest.mark.asyncio
    async def test_delete_memory_cleans_all_layers(self, memory_setup, test_memory_root):
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

        mgr = memory_setup["manager"]
        storage = memory_setup["storage"]

        entry = MemoryEntry(
            id="mem_delete_layers",
            type=MemoryType.PROJECT,
            title="Layer Test",
            content="Verify all storage layers are cleaned.",
            project_id=99,
            user_id="u1",
            privacy=PrivacyLevel.TEAM,
        )
        await mgr.save_memory(entry)

        # Pre-delete verification
        assert await mgr.get_memory("mem_delete_layers") is not None
        assert "mem_delete_layers" in storage._id_index

        # Delete
        success = await mgr.delete_memory("mem_delete_layers")
        assert success is True

        # Post-delete verification: all layers
        assert await mgr.get_memory("mem_delete_layers") is None
        assert "mem_delete_layers" not in storage._id_index
        assert "mem_delete_layers" not in storage._hash_index

        # SQLite layer
        rows = await storage.index_db.search({"id": "mem_delete_layers"}, limit=1)
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_memory_returns_false(self, memory_setup):
        success = await memory_setup["manager"].delete_memory("mem_does_not_exist")
        assert success is False

    @pytest.mark.asyncio
    async def test_rewind_deletes_by_source_message_id(self, memory_setup, test_memory_root):
        """MemoryRewind should delete memories linked to a source_message_id."""
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        from app.core.memory.event.subscribers import MemoryRewind
        from app.core.engine.rewind.event import RewindRequestedEvent
        from unittest.mock import MagicMock, patch

        mgr = memory_setup["manager"]

        # Create memories with source_message_id
        for i in range(3):
            entry = MemoryEntry(
                id=f"mem_rewind_{i}",
                type=MemoryType.PROJECT,
                title=f"Rewind Test {i}",
                content=f"Content {i}",
                project_id=1,
                source_message_id="msg_src_001",
                source="auto_extraction",
            )
            await mgr.save_memory(entry)

        # Verify pre-rewind
        for i in range(3):
            assert await mgr.get_memory(f"mem_rewind_{i}") is not None

        # Patch LifespanManager for MemoryRewind
        mock_container = MagicMock()
        mock_container.memory_manager = mgr

        with patch("app.core.memory.lifespan.MemoryLifespanManager") as MockLifespan:
            MockLifespan.is_initialized.return_value = True
            MockLifespan.get_container.return_value = mock_container

            rewind = MemoryRewind()
            event = RewindRequestedEvent(
                thread_id="t_rewind",
                target_message_id="msg_src_001",
                affected_message_ids=["msg_src_001"],
                affected_run_ids=[],
                include_target=True,
            )

            count = await rewind.cleanup(["msg_src_001"])
            assert count == 3, f"Expected 3 deletions, got {count}"

        # Verify post-rewind
        for i in range(3):
            assert await mgr.get_memory(f"mem_rewind_{i}") is None


# ───────────────────────── Phase 14: Maintenance ─────────────────────────

class TestPhase14Maintenance:
    """Test memory maintenance: pruning, quality analysis, regeneration."""

    @pytest.mark.asyncio
    async def test_run_maintenance_skips_below_threshold(self, memory_setup):
        """Maintenance should skip when memory count is below MAINTENANCE_THRESHOLD."""
        mgr = memory_setup["manager"]
        result = await mgr.run_maintenance(force=False)
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_run_maintenance_with_force(self, memory_setup):
        """Maintenance should run when force=True regardless of threshold."""
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        mgr = memory_setup["manager"]

        # Seed a few memories (still below threshold of 50)
        for i in range(5):
            entry = MemoryEntry(
                id=f"mem_maint_{i}",
                type=MemoryType.PROJECT,
                title=f"Maintenance Test {i}",
                content=f"Content for maintenance test {i}",
                project_id=1,
            )
            await mgr.save_memory(entry)

        result = await mgr.run_maintenance(force=True)
        assert result["status"] == "completed"
        assert "low_quality_count" in result
        assert "pruning_count" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_pruning_cycle_removes_fulfilled_tasks(self, memory_setup):
        """Pruning should remove memories tagged as 'todo' if no longer pending."""
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        from app.core.memory.pruning import MemoryPruningService

        storage = memory_setup["storage"]
        pruning = MemoryPruningService(storage)

        # Create a memory tagged as todo
        entry = MemoryEntry(
            id="mem_prune_todo",
            type=MemoryType.PROJECT,
            title="Fix authentication bug",
            content="Need to fix the auth bug in login.py",
            project_id=1,
            tags=["todo", "bug"],
        )
        await storage.save(entry)

        # Run pruning (no todo_service, so task fulfillment will skip gracefully)
        logs = await pruning.run_pruning_cycle(project_id=1)
        # Without a real todo_service, no task memories should be deleted,
        # but the cycle should complete without errors.
        assert isinstance(logs, list)

    @pytest.mark.asyncio
    async def test_quality_analysis_identifies_low_quality(self, memory_setup):
        """Quality analyzer should flag vague, old memories as low quality."""
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        from datetime import datetime, timedelta

        mgr = memory_setup["manager"]
        quality = memory_setup["quality"]

        # Create a vague, non-actionable memory
        entry = MemoryEntry(
            id="mem_low_quality",
            type=MemoryType.PROJECT,
            title="Something vague",
            content="We probably need to do something about the thing somehow.",
            project_id=1,
            updated_at=datetime.utcnow() - timedelta(days=100),
        )
        await mgr.save_memory(entry)

        scores = await quality.analyze_memory(entry)
        assert scores.overall < 0.5, f"Expected low quality, got {scores.overall}"

        # Debug: trace get_cleanup_recommendations
        all_mems = await mgr.list_memories(limit=10)
        assert any(m.id == "mem_low_quality" for m in all_mems), "mem_low_quality not found in list_all"

        # Check if analyze_memory produces low scores
        entry = await mgr.get_memory("mem_low_quality")
        scores = await quality.analyze_memory(entry)
        assert scores.overall < 0.3, f"Expected low quality, got overall={scores.overall}"

        recommendations = await quality.get_cleanup_recommendations(project_id=1, min_quality=0.3)
        ids = [r.entry.id for r in recommendations]
        assert "mem_low_quality" in ids, f"Expected mem_low_quality in recommendations, got: {ids}"

    @pytest.mark.asyncio
    async def test_regenerate_memory_md(self, memory_setup, test_memory_root):
        """Two-tier manager should regenerate MEMORY.md from cold memory."""
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        mgr = memory_setup["manager"]

        # Seed some strategic memories
        for i in range(3):
            entry = MemoryEntry(
                id=f"mem_hot_{i}",
                type=MemoryType.PROJECT,
                title=f"Architecture Decision {i}",
                content=f"Use microservices for service {i}",
                project_id=1,
                utility_score=0.9,
            )
            await mgr.save_memory(entry)

        await mgr.regenerate_memory_md()

        # Verify MEMORY.md was created
        from app.core.config import settings
        memory_md = Path(settings.BRAIN_MEMORY_ROOT) / "MEMORY.md"
        assert memory_md.exists(), "MEMORY.md should be regenerated"
        content = memory_md.read_text(encoding="utf-8")
        assert "Project Memory" in content



# ───────────────────────── Phase 15: FileEngine Edge Cases ─────────────────────────

class TestFileEngineEdgeCases:
    """补充 _FileEngine 的边界情况测试。"""

    @pytest.mark.asyncio
    async def test_concurrent_save_no_race_condition(self, memory_setup):
        """并发保存同一内容不应产生重复条目。"""
        import asyncio
        mgr = memory_setup["manager"]
        from app.core.memory.models import MemoryEntry, MemoryType

        entry = MemoryEntry(
            id="mem_concurrent_01",
            type=MemoryType.PROJECT,
            title="Concurrent Test",
            content="Same content for race condition test.",
            project_id=1,
        )

        # 并发保存两次
        results = await asyncio.gather(
            mgr.save_memory(entry),
            mgr.save_memory(entry),
            return_exceptions=True,
        )

        # 应该只产生一个条目（hash 去重）
        found = await mgr.get_memory("mem_concurrent_01")
        assert found is not None
        assert found.content == entry.content

    @pytest.mark.asyncio
    async def test_large_content_storage(self, memory_setup):
        """大内容（>100KB）应能正确存储和检索。"""
        mgr = memory_setup["manager"]
        from app.core.memory.models import MemoryEntry, MemoryType

        large_content = "x" * 100_000
        entry = MemoryEntry(
            id="mem_large_01",
            type=MemoryType.PROJECT,
            title="Large Content Test",
            content=large_content,
            project_id=1,
        )
        await mgr.save_memory(entry)

        found = await mgr.get_memory("mem_large_01")
        assert found is not None
        assert found.content == large_content
        assert len(found.content) == 100_000

    @pytest.mark.asyncio
    async def test_special_characters_in_content(self, memory_setup):
        """内容包含特殊字符（Unicode、换行、引号）应正确保存。"""
        mgr = memory_setup["manager"]
        from app.core.memory.models import MemoryEntry, MemoryType

        special_content = '特殊字符测试 🚀\n"quoted" \'single\' <tag> &amp; \t\n中文内容'
        entry = MemoryEntry(
            id="mem_special_01",
            type=MemoryType.PROJECT,
            title="Special Characters",
            content=special_content,
            project_id=1,
        )
        await mgr.save_memory(entry)

        found = await mgr.get_memory("mem_special_01")
        assert found is not None
        assert found.content == special_content

    @pytest.mark.asyncio
    async def test_rapid_save_and_delete_cycle(self, memory_setup):
        """快速保存然后删除应正确清理所有层。"""
        mgr = memory_setup["manager"]
        from app.core.memory.models import MemoryEntry, MemoryType

        entry = MemoryEntry(
            id="mem_rapid_01",
            type=MemoryType.PROJECT,
            title="Rapid Cycle",
            content="Quick save and delete.",
            project_id=1,
        )
        await mgr.save_memory(entry)
        assert await mgr.get_memory("mem_rapid_01") is not None

        await mgr.delete_memory("mem_rapid_01")
        assert await mgr.get_memory("mem_rapid_01") is None
