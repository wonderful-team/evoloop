from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.core.callbacks.database_logger import DatabaseCallbackHandler
from app.infrastructure.database.sql.models import Message


@pytest.mark.asyncio
async def test_database_logging_persistence():
    """
    Verify that DatabaseCallbackHandler correctly persists messages to the DB.
    """
    thread_id = "test-thread-123"
    project_id = 7
    run_id = uuid4()

    handler = DatabaseCallbackHandler(thread_id=thread_id, project_id=project_id, run_id=run_id)

    # Mock LLM Result
    # Simulate an AI response with text and tool calls
    ai_message = AIMessage(
        content="I will update the file.",
        tool_calls=[
            {"name": "manage_file", "args": {"action": "read", "path": "main.py"}, "id": "call_1"}
        ]
    )
    result = LLMResult(generations=[[ChatGeneration(message=ai_message)]])

    # Mock the DB Session
    mock_session = AsyncMock()
    # Mock execute result for parent_id lookup
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None # No parent for first msg
    mock_session.execute.return_value = mock_result

    # Context manager mock for session_scope
    @pytest.fixture
    def mock_session_scope():
        m = MagicMock()
        m.__aenter__.return_value = mock_session
        m.__aexit__.return_value = None
        return m

    # Patch session_scope where it is IMPORTED in database_logger
    with patch("app.core.callbacks.database_logger.session_scope", return_value=AsyncMock()) as mock_scope_factory:
        mock_scope_factory.return_value.__aenter__.return_value = mock_session

        # ACT: Trigger on_llm_end
        await handler.on_llm_end(result, run_id=run_id)

        # ASSERT: Check if session.add was called with a Message
        assert mock_session.add.called

        # Search for Message object in all calls
        message_logged = False
        logged_obj = None
        for call_args in mock_session.add.call_args_list:
            arg = call_args[0][0]
            if isinstance(arg, Message):
                message_logged = True
                logged_obj = arg
                break

        assert message_logged, "Message object was not added to session"
        assert logged_obj.thread_id == thread_id
        assert logged_obj.project_id == project_id
        assert logged_obj.role == "ai"
        assert "I will update the file." in logged_obj.content
        assert "**Action:**" in logged_obj.content
        assert "Read 'main.py'" in logged_obj.content
        assert logged_obj.run_id == run_id

@pytest.mark.asyncio
async def test_database_snapshot_persistence():
    """
    Verify snapshot_tasks_to_last_message updates the DB.
    """
    thread_id = "test-thread-snap"
    handler = DatabaseCallbackHandler(thread_id=thread_id, project_id=1)

    mock_session = AsyncMock()
    mock_db_msg = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_db_msg
    mock_session.execute.return_value = mock_result

    with patch("app.core.callbacks.database_logger.session_scope", return_value=AsyncMock()) as mock_scope_factory:
        mock_scope_factory.return_value.__aenter__.return_value = mock_session

        # Input tasks
        input_tasks = [{"id": "t1", "name": "Task 1", "status": "done"}]
        await handler.snapshot_tasks_to_last_message(input_tasks)

        # Expected output (keys populated by logger)
        expected_tasks = [{
            "id": "t1",
            "name": "Task 1",
            "status": "done",
            "type": None,
            "time": None,
            "details": None
        }]

        assert mock_db_msg.steps_snapshot == expected_tasks
