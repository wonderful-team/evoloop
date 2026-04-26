"""
Integration tests for WebSocket remote command handlers.

Focus: verify that EngineCommandHandler._handle_command correctly delegates to
 dispatch_agent_run for chat_message flows.

Run: cd backend && python -m pytest tests/integration/test_websocket_dispatch.py -v
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


# Pre-import to avoid pkgutil.resolve_name + __getattr__ issues with Pydantic v2
import app.core.engine.command_handler as _ch


@pytest.fixture(autouse=True)
def mock_dispatch():
    """Patch dispatch_agent_run."""
    with patch.object(_ch, "dispatch_agent_run", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_background():
    """Patch run_agent_background."""
    with patch.object(_ch, "run_agent_background", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_dispatch_result():
    """Return a canned DispatchResult."""
    from app.core.engine.dispatch import DispatchResult
    return DispatchResult(
        status="queued",
        thread_id="ws-123",
        message_id=1,
        inputs={"messages": [{"type": "human", "content": "hi"}]},
        error=None,
    )


@pytest.mark.asyncio
async def test_handle_remote_command_chat_message(mock_dispatch, mock_dispatch_result, mock_background):
    """chat_message should call dispatch_agent_run with parsed text."""
    from app.core.engine.command_handler import EngineCommandHandler
    from app.core.evocloud.schemas import RemoteCommand

    mock_dispatch.return_value = mock_dispatch_result

    command = {
        "type": "chat_message",
        "thread_id": "ws-123",
        "message": "Hello from WebSocket",
        "project_id": 42,
        "command_id": 7,
    }

    handler = EngineCommandHandler()
    await handler._handle_command(RemoteCommand.model_validate(command))

    mock_dispatch.assert_awaited_once()
    call_kwargs = mock_dispatch.call_args.kwargs
    assert call_kwargs["thread_id"] == "ws-123"
    assert call_kwargs["message_content"] == "Hello from WebSocket"
    assert call_kwargs["project_id"] == 42
    assert call_kwargs["command_id"] == 7
    assert call_kwargs["model"] is None  # WebSocket does not carry model selection


@pytest.mark.asyncio
async def test_handle_remote_command_with_attachments(mock_dispatch, mock_dispatch_result, mock_background):
    """chat_message with attachments should pass them to dispatch."""
    from app.core.engine.command_handler import EngineCommandHandler
    from app.core.evocloud.schemas import RemoteCommand

    mock_dispatch.return_value = mock_dispatch_result

    command = {
        "type": "chat_message",
        "thread_id": "ws-123",
        "message": "Look at this",
        "attachments": [{"type": "image", "url": "https://example.com/img.png"}],
    }

    handler = EngineCommandHandler()
    await handler._handle_command(RemoteCommand.model_validate(command))

    call_kwargs = mock_dispatch.call_args.kwargs
    assert len(call_kwargs["attachments"]) == 1
    assert call_kwargs["attachments"][0]["type"] == "image"


@pytest.mark.asyncio
async def test_handle_remote_command_nested_content(mock_dispatch, mock_dispatch_result, mock_background):
    """Legacy nested 'content' format should be parsed correctly."""
    from app.core.engine.command_handler import EngineCommandHandler
    from app.core.evocloud.schemas import RemoteCommand

    mock_dispatch.return_value = mock_dispatch_result

    command = {
        "type": "chat_message",
        "thread_id": "ws-123",
        "content": {
            "text": "Nested message",
            "attachments": [],
        },
    }

    handler = EngineCommandHandler()
    await handler._handle_command(RemoteCommand.model_validate(command))

    call_kwargs = mock_dispatch.call_args.kwargs
    assert call_kwargs["message_content"] == "Nested message"


@pytest.mark.asyncio
async def test_handle_remote_command_params_format(mock_dispatch, mock_dispatch_result, mock_background):
    """Params nested inside content should be parsed."""
    from app.core.engine.command_handler import EngineCommandHandler
    from app.core.evocloud.schemas import RemoteCommand

    mock_dispatch.return_value = mock_dispatch_result

    command = {
        "type": "chat_message",
        "thread_id": "ws-123",
        "content": {
            "params": {
                "message": "Param message",
                "attachments": [{"type": "file"}],
            }
        },
    }

    handler = EngineCommandHandler()
    await handler._handle_command(RemoteCommand.model_validate(command))

    call_kwargs = mock_dispatch.call_args.kwargs
    assert call_kwargs["message_content"] == "Param message"
    assert len(call_kwargs["attachments"]) == 1


@pytest.mark.asyncio
async def test_handle_remote_command_no_message_skips(mock_dispatch, mock_background):
    """When no message and no attachments, handler should skip silently."""
    from app.core.engine.command_handler import EngineCommandHandler
    from app.core.evocloud.schemas import RemoteCommand

    command = {
        "type": "chat_message",
        "thread_id": "ws-123",
    }

    handler = EngineCommandHandler()
    await handler._handle_command(RemoteCommand.model_validate(command))

    mock_dispatch.assert_not_awaited()
    mock_background.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_remote_command_dispatches_background(mock_dispatch, mock_dispatch_result, mock_background):
    """On success, handler should schedule run_agent_background."""
    from app.core.engine.command_handler import EngineCommandHandler
    from app.core.evocloud.schemas import RemoteCommand

    mock_dispatch.return_value = mock_dispatch_result

    command = {
        "type": "chat_message",
        "thread_id": "ws-123",
        "message": "Go",
    }

    handler = EngineCommandHandler()
    await handler._handle_command(RemoteCommand.model_validate(command))

    # run_agent_background is scheduled via asyncio.create_task
    # create_task does not await, so assert_called instead of assert_awaited
    mock_background.assert_called_once()


@pytest.mark.asyncio
async def test_handle_remote_command_dispatch_failure(mock_dispatch, mock_background):
    """When dispatch fails, handler should log and not schedule background."""
    from app.core.engine.dispatch import DispatchResult
    from app.core.engine.command_handler import EngineCommandHandler
    from app.core.evocloud.schemas import RemoteCommand

    mock_dispatch.return_value = DispatchResult(
        status="failed",
        thread_id="ws-123",
        error="DB error",
    )

    command = {
        "type": "chat_message",
        "thread_id": "ws-123",
        "message": "Go",
    }

    with pytest.raises(RuntimeError, match="Agent dispatch failed"):
        handler = EngineCommandHandler()
        await handler._handle_command(RemoteCommand.model_validate(command))

    mock_background.assert_not_called()


@pytest.mark.asyncio
async def test_handle_remote_command_hitl_response(mock_background):
    """hitl_response should bypass dispatch and resume directly."""
    from app.core.engine.command_handler import EngineCommandHandler
    from app.core.evocloud.schemas import RemoteCommand

    command = {
        "type": "hitl_response",
        "thread_id": "ws-123",
        "content": {"response": "APPROVED"},
        "command_id": "77",
    }

    handler = EngineCommandHandler()
    await handler._handle_command(RemoteCommand.model_validate(command))

    # create_task does not await
    mock_background.assert_called_once()
    # Verify BackgroundAgentInputs was constructed with hitl_resume_response
    call_args = mock_background.call_args
    assert call_args.args[0] == "ws-123"


@pytest.mark.asyncio
async def test_handle_remote_command_model_fallback(mock_dispatch, mock_dispatch_result, mock_background):
    """
    Regression test: WebSocket commands used to pass model=None which caused
    crashes in run_agent_background. dispatch_agent_run now handles fallback.
    """
    from app.core.engine.dispatch import dispatch_agent_run

    # Call the real dispatch (not mocked) to verify fallback
    with patch("app.core.engine.dispatch.session_scope") as mock_scope:
        session = MagicMock()
        session.get = AsyncMock(return_value=MagicMock())
        session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=0)))
        session.add = MagicMock()
        session.flush = AsyncMock()

        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def _fake():
            yield session
        mock_scope.side_effect = _fake

        with patch("app.core.monitoring.activity.activity_monitor.start_run", new_callable=AsyncMock), \
             patch("app.domain.project.reference_service.reference_service.process_references", new_callable=AsyncMock) as mock_refs, \
             patch("app.infrastructure.config.service.SystemConfigService.get_value", return_value="gpt-4"):

            mock_refs.return_value = MagicMock(content_blocks="hi")

            result = await dispatch_agent_run(
                thread_id="t-123",
                message_content="Hello",
                model=None,
            )

            assert result.status == "queued"
            assert result.inputs["model"] == "gpt-4"
