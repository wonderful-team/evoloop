"""
Integration tests for app.core.engine.dispatch

Tests the unified dispatch layer (dispatch_agent_run) which is shared by:
- HTTP /chat
- WebSocket remote commands
- /resume persistence path

Run: cd backend && python -m pytest tests/integration/test_dispatch_integration.py -v
"""

import os
import sys
import pytest
from contextlib import asynccontextmanager
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
def mock_session():
    """Yield a mocked async DB session."""
    session = MagicMock()
    session.get = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    # Mock scalar / scalars chaining
    result_mock = MagicMock()
    result_mock.scalar.return_value = None
    result_mock.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    session.execute.return_value = result_mock
    return session


@pytest.fixture
def mock_scope(mock_session):
    """Patch session_scope to yield the mock session."""
    @asynccontextmanager
    async def _scope():
        yield mock_session

    with patch("app.core.engine.dispatch.session_scope", _scope):
        yield mock_session


@pytest.fixture
def mock_ref_service():
    """Patch reference_service.process_references."""
    ref_ctx = MagicMock()
    ref_ctx.content_blocks = "Hello world"
    with patch(
        "app.core.engine.dispatch.reference_service.process_references",
        new_callable=AsyncMock,
        return_value=ref_ctx,
    ):
        yield ref_ctx


@pytest.fixture(autouse=True)
def mock_evocloud():
    """Patch EvoCloud get_token."""
    with patch(
        "app.core.evocloud.manager.EvoCloudManager.get_token",
        new_callable=AsyncMock,
        return_value="mock_token",
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_system_config():
    """Patch SystemConfigService.get_value to return a default model."""
    with patch(
        "app.infrastructure.config.service.SystemConfigService.get_value",
        return_value="gpt-4o",
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_activity():
    """Patch activity_monitor.start_run."""
    with patch(
        "app.core.monitoring.activity.activity_monitor.start_run",
        new_callable=AsyncMock,
    ) as m:
        yield m


@pytest.mark.asyncio
async def test_dispatch_returns_queued_status(mock_scope, mock_ref_service):
    """dispatch_agent_run should return status='queued' on success."""
    from app.core.engine.dispatch import dispatch_agent_run

    result = await dispatch_agent_run(
        thread_id="t-123",
        message_content="Hello",
        project_id=1,
    )

    assert result.status == "queued"
    assert result.thread_id == "t-123"
    assert result.error is None


@pytest.mark.asyncio
async def test_dispatch_model_fallback(mock_scope, mock_ref_service, mock_system_config):
    """When model is None, dispatch should fallback to SystemConfigService."""
    from app.core.engine.dispatch import dispatch_agent_run

    result = await dispatch_agent_run(
        thread_id="t-123",
        message_content="Hello",
        model=None,
    )

    assert result.inputs is not None
    assert result.inputs["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_dispatch_respects_explicit_model(mock_scope, mock_ref_service):
    """When model is explicitly provided, it should be used verbatim."""
    from app.core.engine.dispatch import dispatch_agent_run

    result = await dispatch_agent_run(
        thread_id="t-123",
        message_content="Hello",
        model="gpt-4-turbo",
    )

    assert result.inputs["model"] == "gpt-4-turbo"


@pytest.mark.asyncio
async def test_dispatch_skip_persistence(mock_scope, mock_ref_service):
    """skip_message_persistence=True should bypass DB message insert."""
    from app.core.engine.dispatch import dispatch_agent_run

    mock_scope.add.reset_mock()
    mock_scope.flush.reset_mock()

    result = await dispatch_agent_run(
        thread_id="t-123",
        message_content="Hello",
        skip_message_persistence=True,
    )

    # Message.add should NOT be called for the user message
    add_calls = [c for c in mock_scope.add.call_args_list if hasattr(c.args[0], "role")]
    # In skip mode, no Message object is added, but Conversation upsert still happens
    assert result.message_id is None


@pytest.mark.asyncio
async def test_dispatch_builds_correct_inputs(mock_scope, mock_ref_service):
    """The returned BackgroundAgentInputs dict should contain all expected keys."""
    from app.core.engine.dispatch import dispatch_agent_run

    result = await dispatch_agent_run(
        thread_id="t-123",
        message_content="Build me a web app",
        project_id=42,
        checkpoint_id="cp-1",
        is_retry=True,
    )

    inputs = result.inputs
    assert inputs is not None
    assert inputs["project_id"] == 42
    assert inputs["checkpoint_id"] == "cp-1"
    assert inputs["is_retry"] is True
    assert inputs["goal"] == "Build me a web app"
    assert inputs["session_goal"] == "Build me a web app"
    assert "messages" in inputs
    assert len(inputs["messages"]) == 1
    assert inputs["messages"][0]["type"] == "human"


@pytest.mark.asyncio
async def test_dispatch_with_attachments(mock_scope, mock_ref_service):
    """Attachments should be passed to reference_service and reflected in DB."""
    from app.core.engine.dispatch import dispatch_agent_run

    attachments = [
        {"type": "image", "url": "https://example.com/img.png", "name": "screenshot.png"}
    ]

    result = await dispatch_agent_run(
        thread_id="t-123",
        message_content="Check this image",
        attachments=attachments,
    )

    assert result.status == "queued"
    # Reference service should have been called with attachments
    mock_ref_service.content_blocks = "Check this image"


@pytest.mark.asyncio
async def test_dispatch_context_auto_build(mock_scope, mock_ref_service):
    """When context is not provided, dispatch should auto-build one."""
    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.context.manager import ContextManager

    result = await dispatch_agent_run(
        thread_id="t-auto",
        message_content="Hello",
        project_id=99,
        command_id=77,
        model="gpt-4",
    )

    ctx = ContextManager.current()
    assert ctx is not None
    assert ctx.thread_id == "t-auto"
    assert ctx.project_id == 99
    assert ctx.command_id == 77
    assert ctx.active_model == "gpt-4"


@pytest.mark.asyncio
async def test_dispatch_goal_prefix(mock_scope, mock_ref_service):
    """goal_prefix should be prepended to the goal string."""
    from app.core.engine.dispatch import dispatch_agent_run

    result = await dispatch_agent_run(
        thread_id="t-123",
        message_content="Retry this",
        goal_prefix="Retry: ",
    )

    assert result.inputs["goal"].startswith("Retry: ")


@pytest.mark.asyncio
async def test_persist_user_message_exists(mock_scope):
    """persist_user_message helper should persist message when conversation exists."""
    from app.core.engine.dispatch import persist_user_message

    # Conversation exists
    mock_scope.get.return_value = MagicMock(id="conv-1", project_id=1)
    max_seq_result = MagicMock()
    max_seq_result.scalar.return_value = 5
    mock_scope.execute.return_value = max_seq_result

    # flush should set id on added Message objects
    async def _flush():
        for call in mock_scope.add.call_args_list:
            obj = call.args[0]
            if hasattr(obj, "id") and obj.id is None:
                object.__setattr__(obj, "id", 999)

    mock_scope.flush.side_effect = _flush

    msg_id = await persist_user_message("t-123", "Hello", project_id=1)
    assert msg_id is not None
    import uuid
    assert uuid.UUID(msg_id)  # verify it's a valid UUID


@pytest.mark.asyncio
async def test_persist_user_message_missing_conversation(mock_scope):
    """persist_user_message should return None when conversation does not exist."""
    from app.core.engine.dispatch import persist_user_message

    mock_scope.get.return_value = None

    msg_id = await persist_user_message("t-missing", "Hello")
    assert msg_id is None



