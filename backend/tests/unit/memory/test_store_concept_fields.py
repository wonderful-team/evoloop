"""Tests for MemoryManager.store_concept source/member/kind fields."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.memory.manager import MemoryManager
from app.core.memory.models import MemoryEntry, MemoryType


@pytest.fixture
def manager():
    storage = MagicMock()
    storage.save = AsyncMock()
    storage._db_upsert = AsyncMock()
    return MemoryManager(storage=storage)


@pytest.mark.asyncio
async def test_store_concept_persists_source_and_kind(manager):
    with patch.object(manager, "save_memory", new_callable=AsyncMock) as mock_save:
        concept = await manager.store_concept(
            concept="Important requirement",
            description="Important requirement",
            project_id=7,
            member_id=42,
            source_message_id="msg-42",
            source_thread_id="thread-7",
            created_by_member_id=42,
            memory_kind="concept",
        )

    assert isinstance(concept, MemoryEntry)
    assert concept.type == MemoryType.CONCEPT
    assert concept.member_id == 42
    assert concept.created_by_member_id == 42
    assert concept.memory_kind == "concept"
    assert concept.source_message_id == "msg-42"
    assert concept.source_thread_id == "thread-7"
    mock_save.assert_awaited_once_with(concept)


@pytest.mark.asyncio
async def test_store_concept_defaults_created_by_to_member_id(manager):
    with patch.object(manager, "save_memory", new_callable=AsyncMock) as mock_save:
        concept = await manager.store_concept(
            concept="Fallback member",
            member_id=5,
        )

    assert concept.created_by_member_id == 5
    assert concept.memory_kind == "concept"
    mock_save.assert_awaited_once_with(concept)
