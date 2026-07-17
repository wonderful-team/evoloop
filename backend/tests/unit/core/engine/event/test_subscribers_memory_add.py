"""Tests for remember (memory_add) toggle behavior."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.engine.event.handlers.memory import MemoryCommandHandler
from app.core.evocloud.schemas import RemoteCommand
from app.models.conversation import Message


@pytest.fixture
def subscriber():
    return MemoryCommandHandler()


@pytest.fixture
def mock_memory_manager():
    manager = MagicMock()
    manager.store_concept = AsyncMock(return_value=MagicMock(id="concept_msg_1"))
    manager.delete_memory = AsyncMock(return_value=True)
    manager.get_memory = AsyncMock(return_value=None)
    storage = MagicMock()
    storage._db_search = AsyncMock(return_value=[])
    manager._storage = storage
    return manager


@pytest.mark.asyncio
async def test_handle_memory_add_creates_concept_and_marks_message(subscriber, mock_memory_manager):
    cmd = RemoteCommand(
        action="memory_add",
        thread_id="thread-1",
        project_id=1,
        content={
            "name": "hello world",
            "description": "hello world",
            "source_message_id": "msg-1",
            "source_thread_id": "thread-1",
            "created_by_member_id": 42,
        },
    )

    with patch("app.core.memory.lifespan.MemoryLifespanManager.get_manager", return_value=mock_memory_manager), \
         patch("app.core.engine.event.handlers.memory.session_scope") as mock_scope:
        mock_session = MagicMock()
        mock_result = MagicMock()
        msg = Message(
            id="msg-1",
            thread_id="thread-1",
            role="human",
            content="hello world",
            member_id=42,
            project_id=1,
        )
        mock_result.scalar_one_or_none.return_value = msg
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

        await subscriber._handle_memory_add(cmd)

    mock_memory_manager.store_concept.assert_awaited_once()
    call_kwargs = mock_memory_manager.store_concept.await_args.kwargs
    assert call_kwargs["concept"] == "hello world"
    assert call_kwargs["source_message_id"] == "msg-1"
    assert call_kwargs["source_thread_id"] == "thread-1"
    assert call_kwargs["created_by_member_id"] == 42
    assert call_kwargs["memory_kind"] == "concept"
    assert msg.is_remembered is True
    assert msg.memory_concept_id == "concept_msg_1"
    assert msg.remembered_at is not None


@pytest.mark.asyncio
async def test_handle_memory_add_toggles_off_existing_concept(subscriber, mock_memory_manager):
    existing = MagicMock(id="concept_existing", title="hello world")
    mock_memory_manager._storage._db_search = AsyncMock(return_value=[{"id": "concept_existing"}])
    mock_memory_manager.get_memory = AsyncMock(return_value=existing)

    cmd = RemoteCommand(
        action="memory_add",
        thread_id="thread-1",
        project_id=1,
        content={
            "name": "hello world",
            "description": "hello world",
            "source_message_id": "msg-1",
            "source_thread_id": "thread-1",
            "created_by_member_id": 42,
        },
    )

    with patch("app.core.memory.lifespan.MemoryLifespanManager.get_manager", return_value=mock_memory_manager), \
         patch("app.core.engine.event.handlers.memory.session_scope") as mock_scope:
        mock_session = MagicMock()
        mock_result = MagicMock()
        msg = Message(
            id="msg-1",
            thread_id="thread-1",
            role="human",
            content="hello world",
            member_id=42,
            project_id=1,
            is_remembered=True,
            memory_concept_id="concept_existing",
            remembered_at=datetime.now(timezone.utc),
        )
        mock_result.scalar_one_or_none.return_value = msg
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

        await subscriber._handle_memory_add(cmd)

    mock_memory_manager.delete_memory.assert_awaited_once_with("concept_existing")
    assert msg.is_remembered is False
    assert msg.memory_concept_id is None
    assert msg.remembered_at is None


@pytest.mark.asyncio
async def test_handle_memory_add_without_source_message_id_still_creates_concept(subscriber, mock_memory_manager):
    cmd = RemoteCommand(
        action="memory_add",
        thread_id="thread-1",
        project_id=1,
        content={
            "name": "note",
            "description": "note content",
        },
    )

    with patch("app.core.memory.lifespan.MemoryLifespanManager.get_manager", return_value=mock_memory_manager), \
         patch("app.core.engine.event.handlers.memory.session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

        await subscriber._handle_memory_add(cmd)

    mock_memory_manager.store_concept.assert_awaited_once()
    mock_scope.return_value.__aenter__.assert_not_awaited()
