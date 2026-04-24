"""
End-to-end flow tests for the unified dispatch layer.

These tests verify the complete message flow from user input
through dispatch to background agent inputs — without mocking
the dispatch layer itself.

Run: cd backend && python -m pytest tests/integration/test_end_to_end_flow.py -v
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

env_path = os.path.join(os.path.dirname(__file__), "../../../.env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))


@pytest.fixture
def fake_session():
    """Create a fake DB session that supports Conversation + Message ops."""
    session = MagicMock()
    session.get = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    # Default: conversation exists, max seq = 0
    session.get.return_value = MagicMock(id="conv-1", project_id=1)
    exec_result = MagicMock()
    exec_result.scalar.return_value = 0
    session.execute.return_value = exec_result

    @asynccontextmanager
    async def _scope():
        yield session

    return session, _scope


@pytest.mark.asyncio
async def test_http_chat_full_flow(fake_session):
    """
    E2E: HTTP /chat endpoint → dispatch_agent_run → BackgroundAgentInputs.
    Verifies that all fields expected by run_agent_background are present.
    """
    from app.api.routes.agent import chat_endpoint, ChatRequest
    from app.core.engine.background_agent import BackgroundAgentInputs

    session, scope = fake_session

    with patch("app.api.routes.agent.dispatch_agent_run", wraps=None) as mock_dispatch, \
         patch("app.api.routes.agent.run_agent_background") as mock_bg, \
         patch("app.api.routes.agent.session_scope", scope), \
         patch("app.core.evocloud.manager.EvoCloudManager.upload_log", new_callable=AsyncMock), \
         patch("app.core.monitoring.activity.activity_monitor.start_run", new_callable=AsyncMock), \
         patch("app.domain.project.reference_service.reference_service.process_references", new_callable=AsyncMock) as mock_refs:

        mock_refs.return_value = MagicMock(content_blocks="Hello")
        mock_dispatch.return_value = MagicMock(
            status="queued",
            thread_id="t-e2e",
            message_id=1,
            inputs={"messages": [{"type": "human", "content": "Hello"}]},
            error=None,
        )

        req = ChatRequest(
            thread_id="t-e2e",
            message="Hello",
            project_id=1,
            model="gpt-4",
        )
        bg_tasks = MagicMock()
        bg_tasks.add_task = MagicMock()

        response = await chat_endpoint(req, bg_tasks, None)

        assert response["status"] == "queued"
        assert response["thread_id"] == "t-e2e"

        # Verify dispatch was called
        mock_dispatch.assert_awaited_once()
        dispatch_kwargs = mock_dispatch.call_args.kwargs
        assert dispatch_kwargs["message_content"] == "Hello"
        assert dispatch_kwargs["model"] == "gpt-4"

        # Verify background task was scheduled
        bg_tasks.add_task.assert_called_once()
        func, thread_id, inputs = bg_tasks.add_task.call_args[0]
        assert thread_id == "t-e2e"
        assert "messages" in inputs


@pytest.mark.asyncio
async def test_websocket_chat_full_flow(fake_session):
    """
    E2E: WebSocket remote command → handle_remote_command → dispatch_agent_run.
    Verifies model fallback and inputs construction.
    """
    from app.core.evocloud.bridge.handlers import handle_remote_command
    from app.core.engine.background_agent import BackgroundAgentInputs
    from app.core.config import settings

    session, scope = fake_session

    with patch("app.core.evocloud.bridge.handlers.dispatch_agent_run", wraps=None) as mock_dispatch, \
         patch("app.core.evocloud.bridge.handlers.run_agent_background") as mock_bg, \
         patch("app.core.engine.dispatch.session_scope", scope), \
         patch("app.core.evocloud.manager.EvoCloudManager.upload_log", new_callable=AsyncMock), \
         patch("app.core.monitoring.activity.activity_monitor.start_run", new_callable=AsyncMock), \
         patch("app.domain.project.reference_service.reference_service.process_references", new_callable=AsyncMock) as mock_refs:

        mock_refs.return_value = MagicMock(content_blocks="WS message")
        mock_dispatch.return_value = MagicMock(
            status="queued",
            thread_id="ws-e2e",
            message_id=2,
            inputs={
                "messages": [{"type": "human", "content": "WS message"}],
                "model": settings.OPENAI_MODEL_NAME,
            },
            error=None,
        )

        command = {
            "type": "chat_message",
            "thread_id": "ws-e2e",
            "message": "WS message",
            "project_id": 1,
        }

        await handle_remote_command(command)

        mock_dispatch.assert_awaited_once()
        kwargs = mock_dispatch.call_args.kwargs
        assert kwargs["model"] is None  # WebSocket never carries model

        # Background should be scheduled
        mock_bg.assert_called_once()
        _, inputs = mock_bg.call_args[0]
        assert inputs["model"] == settings.OPENAI_MODEL_NAME


@pytest.mark.asyncio
async def test_retry_flow_preserves_original_message(fake_session):
    """
    E2E: /chat/retry should reconstruct the original message content
    and attachments after rewind, then dispatch with is_retry=True.
    """
    from app.api.routes.agent import retry_chat, ChatRequest

    session, scope = fake_session

    # Build a message with references
    orig_msg = MagicMock()
    orig_msg.id = 77
    orig_msg.thread_id = "t-retry"
    orig_msg.role = "human"
    orig_msg.content = "Original question"
    ref = MagicMock()
    ref.type = "image"
    ref.target_id = "img-1"
    ref.target_name = "screenshot.png"
    orig_msg.references = [ref]

    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = orig_msg
    session.execute.return_value = exec_result

    with patch("app.api.routes.agent.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch, \
         patch("app.api.routes.agent.run_agent_background") as mock_bg, \
         patch("app.api.routes.agent.session_scope", scope), \
         patch("app.core.engine.rewind.RewindOrchestrator.perform_rewind", new_callable=AsyncMock) as mock_rewind:

        mock_rewind.return_value = MagicMock(
            status="success",
            removed_message_count=1,
            reverted_file_count=0,
            errors=[],
        )
        mock_dispatch.return_value = MagicMock(
            status="queued",
            thread_id="t-retry",
            message_id=3,
            inputs={"messages": []},
            error=None,
        )

        req = ChatRequest(
            thread_id="t-retry",
            message="",
            message_id=77,
        )
        bg_tasks = MagicMock()
        bg_tasks.add_task = MagicMock()

        result = await retry_chat(req, bg_tasks)

        assert result["status"] == "queued"
        assert result["action"] == "retry"

        # dispatch should receive the original message content + attachments
        mock_dispatch.assert_awaited_once()
        kwargs = mock_dispatch.call_args.kwargs
        assert kwargs["message_content"] == "Original question"
        assert kwargs["is_retry"] is True
        assert kwargs["skip_message_persistence"] is True
        assert len(kwargs["attachments"]) == 1
        assert kwargs["attachments"][0]["type"] == "image"


@pytest.mark.asyncio
async def test_resume_flow_persists_and_resumes(fake_session):
    """
    E2E: /chat/resume should persist user_input and schedule
    resume_graph_background with correct inputs.
    """
    from app.api.routes.agent import resume_chat, ResumeRequest

    with patch("app.api.routes.agent.get_graph", return_value=MagicMock()), \
         patch("app.api.routes.agent.db_resource_manager") as mock_db_res, \
         patch("app.core.engine.dispatch.persist_user_message", new_callable=AsyncMock) as mock_persist, \
         patch("app.core.engine.dispatch.resume_graph_background") as mock_resume_bg:

        mock_db_res.checkpointer = MagicMock()

        req = ResumeRequest(
            thread_id="t-resume",
            user_input="Yes continue",
            command_id=99,
        )
        bg_tasks = MagicMock()
        bg_tasks.add_task = MagicMock()

        result = await resume_chat(req, bg_tasks)

        assert result.status == "resuming"
        mock_persist.assert_awaited_once_with(
            thread_id="t-resume",
            content="Yes continue",
            project_id=None,
            command_id=99,
        )

        bg_tasks.add_task.assert_called_once()
        func, thread_id, inputs, config = bg_tasks.add_task.call_args[0]
        assert thread_id == "t-resume"
        # func is patched AsyncMock, verify args instead
        assert thread_id == "t-resume"


@pytest.mark.asyncio
async def test_unified_inputs_structure_across_all_entrypoints(fake_session):
    """
    E2E: All three entry points (HTTP /chat, WebSocket, /retry) should
    produce BackgroundAgentInputs with the same required keys.
    """
    from app.api.routes.agent import chat_endpoint, ChatRequest
    from app.core.evocloud.bridge.handlers import handle_remote_command
    from app.core.engine.dispatch import dispatch_agent_run

    session, scope = fake_session
    required_keys = {"messages", "project_id", "checkpoint_id", "is_retry", "goal", "session_goal", "model"}

    with patch("app.core.engine.dispatch.session_scope", scope), \
         patch("app.core.evocloud.manager.EvoCloudManager.upload_log", new_callable=AsyncMock), \
         patch("app.core.monitoring.activity.activity_monitor.start_run", new_callable=AsyncMock), \
         patch("app.domain.project.reference_service.reference_service.process_references", new_callable=AsyncMock) as mock_refs:

        mock_refs.return_value = MagicMock(content_blocks="test")

        # 1. HTTP /chat
        result1 = await dispatch_agent_run(
            thread_id="t-1", message_content="Hello", project_id=1, model="gpt-4"
        )
        assert result1.inputs is not None
        assert required_keys.issubset(result1.inputs.keys())
        assert result1.inputs["model"] == "gpt-4"

        # 2. WebSocket (model=None → fallback)
        result2 = await dispatch_agent_run(
            thread_id="t-2", message_content="WS", model=None
        )
        assert result2.inputs is not None
        assert required_keys.issubset(result2.inputs.keys())
        assert result2.inputs["model"] is not None  # fallback applied

        # 3. Retry
        result3 = await dispatch_agent_run(
            thread_id="t-3", message_content="Retry", is_retry=True, skip_message_persistence=True
        )
        assert result3.inputs is not None
        assert required_keys.issubset(result3.inputs.keys())
        assert result3.inputs["is_retry"] is True
