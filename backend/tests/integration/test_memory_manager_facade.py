"""Coverage for the unified memory facade (MemoryManager) and the global
memory switch (ENABLE_MEMORY).

These tests run in-process against an isolated temp memory root (never the
real ~/.evoloop data) and do not require a running service.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.memory.manager import MemoryManager
from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
from app.core.memory.store import MemoryStore


@pytest.fixture
def mem_store(tmp_path, test_session_scope, monkeypatch):
    # Route file_engine DB-index writes to the test SQLite DB instead of the
    # global resource manager (which is not initialized in-process).
    import app.core.memory.file_engine as file_engine_module

    monkeypatch.setattr(file_engine_module, "session_scope", test_session_scope)
    # Enable memory writes for facade round-trip tests (global switch is off by default).
    monkeypatch.setattr(settings, "ENABLE_MEMORY", True)
    store = MemoryStore(base_dir=str(tmp_path))
    return store


def _concept_entry(name: str = "demo-concept", content: str = "demo content") -> MemoryEntry:
    return MemoryEntry(
        id=f"concept_{name}",
        type=MemoryType.CONCEPT,
        privacy=PrivacyLevel.TEAM,
        title=name,
        content=content,
        description=content[:200],
        project_id=1,
        member_id=0,
        memory_kind="concept",
        tags=["concept"],
    )


class TestMemoryManagerFacade:
    """Core MemoryManager public methods round-trip via MemoryStore."""

    async def test_store_and_retrieve_entry(self, mem_store) -> None:
        manager = MemoryManager(storage=mem_store)
        await manager.initialize()

        await manager.save_memory(_concept_entry("alpha"))
        got = await manager.get_memory("concept_alpha")
        assert got is not None
        assert got.title == "alpha"
        assert got.content == "demo content"


    async def test_store_concept_then_search(self, mem_store) -> None:
        manager = MemoryManager(storage=mem_store)
        await manager.initialize()

        await manager.store_concept(concept="postgres-connection", description="pool details", project_id=1)
        results = await manager.search_concepts("postgres", project_id=1)
        assert any(c.name == "postgres-connection" for c in results)


    async def test_delete_memory(self, mem_store) -> None:
        manager = MemoryManager(storage=mem_store)
        await manager.initialize()

        await manager.save_memory(_concept_entry("doomed"))
        assert await manager.delete("concept_doomed") is True
        assert await manager.get_memory("concept_doomed") is None



class TestMemorySwitch:
    """ENABLE_MEMORY=False must block writes and tool registration."""

    async def test_store_save_is_noop_when_disabled(self, tmp_path, test_session_scope, monkeypatch) -> None:
        monkeypatch.setattr(settings, "ENABLE_MEMORY", False)
        import app.core.memory.file_engine as file_engine_module

        monkeypatch.setattr(file_engine_module, "session_scope", test_session_scope)
        store = MemoryStore(base_dir=str(tmp_path))
        await store.initialize()
        before = sorted(p.name for p in store._engine.root.rglob("*.md"))
        await store.save(_concept_entry("blocked"))
        after = sorted(p.name for p in store._engine.root.rglob("*.md"))
        assert before == after

    async def test_store_save_writes_when_enabled(self, tmp_path, test_session_scope, monkeypatch) -> None:
        monkeypatch.setattr(settings, "ENABLE_MEMORY", True)
        import app.core.memory.file_engine as file_engine_module

        monkeypatch.setattr(file_engine_module, "session_scope", test_session_scope)
        store = MemoryStore(base_dir=str(tmp_path))
        await store.initialize()
        before = sorted(p.name for p in store._engine.root.rglob("*.md"))
        await store.save(_concept_entry("allowed"))
        after = sorted(p.name for p in store._engine.root.rglob("*.md"))
        assert after != before

    def test_public_init_no_longer_exports_internal_symbols(self) -> None:
        import app.core.memory as memory_pkg

        assert "TwoTierMemoryManager" not in dir(memory_pkg)
        assert "MemorySection" not in dir(memory_pkg)
        assert "SectionBudget" not in dir(memory_pkg)

    def test_container_has_no_two_tier_manager_property(self) -> None:
        from app.core.memory.container import MemoryContainer

        assert not hasattr(MemoryContainer, "two_tier_manager")
