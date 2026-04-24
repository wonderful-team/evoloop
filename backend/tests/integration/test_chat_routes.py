"""
Integration tests for HTTP chat routes (/chat, /retry, /resume).

Focus: verify that endpoints correctly delegate to dispatch_agent_run
and schedule background tasks.

Run: cd backend && python -m pytest tests/integration/test_chat_routes.py -v
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

env_path = os.path.join(os.path.dirname(__file__), "../../../.env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))


@pytest.fixture
def mock_dispatch_result():
    """Return a canned DispatchResult."""
    from app.core.engine.dispatch import DispatchResult
    return DispatchResult(
        status="queued",
        thread_id="t-123",
        message_id=42,
        inputs={"messages": [{"type": "human", "content": "hi"}]},
        error=None,
    )


@pytest.fixture(autouse=True)
def mock_dispatch():
    """Patch dispatch_agent_run."""
    with patch(
        "app.api.routes.agent.dispatch_agent_run",
        new_callable=AsyncMock,
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_background():
    """Patch run_agent_background."""
    with patch(
        "app.api.routes.agent.run_agent_background",
        new_callable=AsyncMock,
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_activity():
    """Patch activity_monitor.stop_run."""
    with patch(
        "app.api.routes.agent.activity_monitor.stop_run",
        new_callable=AsyncMock,
    ) as m:
        yield m


@pytest.fixture
def bg_tasks():
    """FastAPI BackgroundTasks mock that exposes added tasks."""
    from fastapi import BackgroundTasks
    tasks = BackgroundTasks()
    # Monkey-patch to record calls for assertion
    tasks._tasks = []
    original_add = tasks.add_task

    def _add_task(func, *args, **kwargs):
        tasks._tasks.append((func, args, kwargs))
        return original_add(func, *args, **kwargs)

    tasks.add_task = _add_task
    return tasks


@pytest.mark.asyncio
async def test_chat_endpoint_calls_dispatch(mock_dispatch, mock_dispatch_result, bg_tasks):
    """/chat should call dispatch_agent_run with correct parameters."""
    from app.api.routes.agent import chat_endpoint, ChatRequest

    mock_dispatch.return_value = mock_dispatch_result

    req = ChatRequest(
        thread_id="t-123",
        message="Hello",
        project_id=42,
        model="gpt-4",
        command_id=7,
        checkpoint_id="cp-1",
    )

    result = await chat_endpoint(req, bg_tasks, None)

    assert result["status"] == "queued"
    assert result["thread_id"] == "t-123"
    assert result["message_id"] == 42

    mock_dispatch.assert_awaited_once()
    call_kwargs = mock_dispatch.call_args.kwargs
    assert call_kwargs["thread_id"] == "t-123"
    assert call_kwargs["message_content"] == "Hello"
    assert call_kwargs["project_id"] == 42
    assert call_kwargs["model"] == "gpt-4"
    assert call_kwargs["command_id"] == 7
    assert call_kwargs["checkpoint_id"] == "cp-1"


@pytest.mark.asyncio
async def test_chat_endpoint_schedules_background_task(mock_dispatch, mock_dispatch_result, bg_tasks):
    """/chat should add run_agent_background to bg_tasks."""
    from app.api.routes.agent import chat_endpoint, ChatRequest

    mock_dispatch.return_value = mock_dispatch_result

    req = ChatRequest(thread_id="t-123", message="Hello")
    await chat_endpoint(req, bg_tasks, None)

    # bg_tasks should have at least one task registered
    assert len(bg_tasks._tasks) >= 1
    func, args, kwargs = bg_tasks._tasks[0]
    # func is the mocked AsyncMock, verify args instead
    assert args[0] == "t-123"
    assert args[0] == "t-123"


@pytest.mark.asyncio
async def test_chat_endpoint_returns_error_when_dispatch_fails(mock_dispatch, bg_tasks):
    """When dispatch returns failed status, /chat should raise HTTPException(500)."""
    from app.api.routes.agent import chat_endpoint, ChatRequest
    from fastapi import HTTPException

    from app.core.engine.dispatch import DispatchResult
    mock_dispatch.return_value = DispatchResult(
        status="failed",
        thread_id="t-123",
        error="DB is down",
    )

    req = ChatRequest(thread_id="t-123", message="Hello")
    with pytest.raises(HTTPException) as exc_info:
        await chat_endpoint(req, bg_tasks, None)

    assert exc_info.value.status_code == 500
    assert "DB is down" in exc_info.value.detail


@pytest.mark.asyncio
async def test_retry_endpoint_calls_dispatch(mock_dispatch, mock_dispatch_result, bg_tasks):
    """/chat/retry should call dispatch_agent_run after rewind logic."""
    from app.api.routes.agent import retry_chat, ChatRequest

    mock_dispatch.return_value = mock_dispatch_result

    # Patch rewind-related calls to avoid actual DB/graph interactions
    with patch("app.api.routes.agent.session_scope") as mock_session_scope, \
         patch("app.core.engine.rewind.RewindOrchestrator.perform_rewind", new_callable=AsyncMock) as mock_rewind:

        # Mock session returning a human message
        session = MagicMock()
        session.execute = AsyncMock()
        msg = MagicMock()
        msg.id = 99
        msg.thread_id = "t-123"
        msg.role = "human"
        msg.content = "Original message"
        msg.references = []
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = msg
        session.execute.return_value = result_mock

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _fake_scope():
            yield session

        mock_session_scope.side_effect = _fake_scope

        mock_rewind.return_value = MagicMock(
            status="success",
            removed_message_count=2,
            reverted_file_count=1,
            errors=[],
        )

        req = ChatRequest(
            thread_id="t-123",
            message="",
            message_id=99,
        )

        result = await retry_chat(req, bg_tasks)

        assert result["status"] == "queued"
        assert result["action"] == "retry"

        # dispatch should be called with is_retry=True and skip_message_persistence=True
        mock_dispatch.assert_awaited_once()
        call_kwargs = mock_dispatch.call_args.kwargs
        assert call_kwargs["is_retry"] is True
        assert call_kwargs["skip_message_persistence"] is True
        assert call_kwargs["goal_prefix"] == "Retry: "


@pytest.mark.asyncio
async def test_resume_endpoint_persists_message(mock_dispatch, bg_tasks):
    """/chat/resume should call persist_user_message when user_input is provided."""
    from app.api.routes.agent import resume_chat, ResumeRequest

    with patch("app.api.routes.agent.get_graph", return_value=MagicMock()), \
         patch("app.api.routes.agent.db_resource_manager") as mock_db_res, \
         patch("app.core.engine.dispatch.persist_user_message", new_callable=AsyncMock) as mock_persist:

        mock_db_res.checkpointer = MagicMock()

        req = ResumeRequest(thread_id="t-123", user_input="Continue please")
        result = await resume_chat(req, bg_tasks)

        assert result.status == "resuming"
        assert result.thread_id == "t-123"
        mock_persist.assert_awaited_once_with(
            thread_id="t-123",
            content="Continue please",
            project_id=None,
            command_id=None,
        )


@pytest.mark.asyncio
async def test_resume_endpoint_with_temp_project(mock_dispatch, bg_tasks):
    """/chat/resume should parse temp_project JSON and set context."""
    from app.api.routes.agent import resume_chat, ResumeRequest

    with patch("app.api.routes.agent.get_graph", return_value=MagicMock()), \
         patch("app.api.routes.agent.db_resource_manager") as mock_db_res, \
         patch("app.api.routes.agent.thread_context_store") as mock_store, \
         patch("app.core.engine.dispatch.persist_user_message", new_callable=AsyncMock):

        mock_db_res.checkpointer = MagicMock()

        payload = '{"type":"temp_project","project_id":99,"project_name":"TestProj"}'
        req = ResumeRequest(thread_id="t-123", user_input=payload)
        result = await resume_chat(req, bg_tasks)

        assert result.status == "resuming"
        mock_store.set_temp_project.assert_called_once_with("t-123", 99)


@pytest.mark.asyncio
async def test_resume_endpoint_smart_tool_completion(bg_tasks):
    """When last message has pending tool_call, resume should inject ToolMessage."""
    from app.api.routes.agent import resume_chat, ResumeRequest
    from langchain_core.messages import AIMessage, ToolMessage

    ai_msg = AIMessage(
        content="Need confirm",
        tool_calls=[{"id": "tc-1", "name": "request_approval", "args": {}}],
    )
    mock_state = MagicMock()
    mock_state.values = {"messages": [ai_msg]}
    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=mock_state)

    with patch("app.api.routes.agent.get_graph", return_value=mock_graph), \
         patch("app.api.routes.agent.db_resource_manager") as mock_db_res, \
         patch("app.core.engine.dispatch.persist_user_message", new_callable=AsyncMock):

        mock_db_res.checkpointer = MagicMock()

        req = ResumeRequest(thread_id="t-123", user_input="APPROVED")
        result = await resume_chat(req, bg_tasks)

        assert result.status == "resuming"
        # The bg task should be scheduled with ToolMessage instead of HumanMessage
        assert len(bg_tasks._tasks) >= 1
        _, args, _ = bg_tasks._tasks[0]
        inputs = args[1]
        assert inputs is not None
        assert "messages" in inputs
        assert isinstance(inputs["messages"][0], ToolMessage)
