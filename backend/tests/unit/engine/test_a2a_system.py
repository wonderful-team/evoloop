import pytest
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.context.manager import ContextManager, EvoContext
from app.core.exceptions import AgentHumanInterruptException, AgentCancelledException
from app.core.evocloud.manager import evocloud_manager
from app.core.evocloud.schemas import RemoteCommand, AgentTask, AgentTaskResult, TaskAttachment
from app.models import Conversation, Message

# Import the tools to register them
from app.core.engine.tools.a2a import list_agents, send_agent_task, complete_task
from app.core.engine.event.subscribers import EngineCommandSubscriber
from app.core.engine.event.handlers.a2a import A2ACommandHandler


@pytest.fixture
def mock_session():
    """Mock database session_scope to prevent 'NoneType' object is not callable errors."""
    session = MagicMock()
    session.get = AsyncMock(return_value=None)  # Default to None so get/create checks work
    
    mock_result = MagicMock()
    mock_result.scalar.return_value = None
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def _scope():
        yield session

    with patch("app.infrastructure.database.session_scope", _scope), \
         patch("app.core.engine.dispatch.session_scope", _scope), \
         patch("app.core.engine.message.sequence.session_scope", _scope), \
         patch("app.core.engine.message.repository.session_scope", _scope), \
         patch("app.core.engine.event.handlers.a2a.session_scope", _scope):
        yield session


@pytest.mark.asyncio
async def test_list_agents_tool():
    """Verify ListAgentsTool queries devices and filters them correctly."""
    mock_devices = {
        "code": 0,
        "data": {
            "list": [
                {
                    "device_key": "dev-1",
                    "device_name": "Desktop 1",
                    "device_type": "desktop",
                    "status": "online",
                    "capabilities": ["code_build"]
                },
                {
                    "device_key": "dev-2",
                    "device_name": "Server 1",
                    "device_type": "server",
                    "status": "offline",
                    "capabilities": ["deployment"]
                },
                {
                    "device_key": "dev-3",
                    "device_name": "Raspberry Pi",
                    "device_type": "embedded",
                    "status": "online",
                    "capabilities": ["gpio_ops"]
                },
                {
                    "device_key": "dev-4",
                    "device_name": "Android Phone Agent",
                    "device_type": "android",
                    "status": "online",
                    "capabilities": ["gui_control"]
                },
                {
                    "device_key": "dev-5",
                    "device_name": "User iPhone",
                    "device_type": "mobile",
                    "status": "online",
                    "capabilities": []
                },
                {
                    "device_key": "dev-6",
                    "device_name": "Unknown Device",
                    "device_type": "unknown",
                    "status": "online",
                    "capabilities": []
                }
            ]
        }
    }

    with patch.object(evocloud_manager.api, "get_devices", AsyncMock(return_value=mock_devices)):
        res = await list_agents.ainvoke({})
        agents = json.loads(res)
        assert len(agents) == 3
        assert agents[0]["device_key"] == "dev-1"
        assert agents[0]["capabilities"] == ["code_build"]
        assert agents[1]["device_key"] == "dev-3"
        assert agents[1]["device_type"] == "embedded"
        assert agents[2]["device_key"] == "dev-4"
        assert agents[2]["device_type"] == "android"


@pytest.mark.asyncio
async def test_send_agent_task_tool(mock_session):
    """Verify SendAgentTaskTool dispatches tasks and suspends execution."""
    thread_id = f"thread-{uuid.uuid4().hex[:8]}"
    ctx = EvoContext(thread_id=thread_id, project_id=DEFAULT_PROJECT_ID, run_id="run-1")
    ContextManager.set(ctx)

    # Set up mock DB returns (return a mock parent conversation)
    mock_conv = Conversation(
        id=thread_id,
        project_id=DEFAULT_PROJECT_ID,
        title="Parent Task",
        root_thread_id=None,
        parent_thread_id=None
    )
    mock_session.get.return_value = mock_conv

    # Mock file upload & gateway sending
    mock_upload = AsyncMock(return_value={
        "filename": "test.txt",
        "download_url": "http://mock/test.txt",
        "file_size": 100,
        "md5": "abc"
    })
    mock_send = AsyncMock()

    with patch.object(evocloud_manager.api, "upload_file", mock_upload), \
         patch.object(evocloud_manager.api, "send_command_to_device", mock_send):
        
        # Expect graph suspension via AgentHumanInterruptException
        with pytest.raises(AgentHumanInterruptException):
            await send_agent_task.coroutine(
                target_device_key="worker-key",
                instruction="Build the package",
                attachments=["/mock/test.txt"]
            )

        # Check upload was called
        mock_upload.assert_called_once_with("/mock/test.txt")
        # Check command sent
        assert mock_send.call_count == 1
        call_args = mock_send.call_args[1]
        assert call_args["device_key"] == "worker-key"
        
        cmd_payload = call_args["cmd_data"]
        assert cmd_payload["action"] == "a2a_task"
        task_data = cmd_payload["content"]
        assert task_data["instruction"] == "Build the package"
        assert task_data["parent_thread_id"] == thread_id
        assert len(task_data["attachments"]) == 1
        assert task_data["attachments"][0]["filename"] == "test.txt"


@pytest.mark.asyncio
async def test_handle_a2a_task_subscriber(mock_session):
    """Verify subscriber handles a2a_task, configures context, and dispatches."""
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    
    # Construct task command
    task_envelope = AgentTask(
        task_id=task_id,
        instruction="Run tests",
        caller_role="desktop",
        global_goal="Run all unit tests",
        attachments=[],
        caller_device_key="caller-key",
        root_thread_id="root-123",
        parent_thread_id="parent-123"
    )

    cmd = RemoteCommand(
        action="a2a_task",
        content=task_envelope.model_dump(),
        thread_id=task_id,
        project_id=DEFAULT_PROJECT_ID
    )

    subscriber = A2ACommandHandler()

    # Mock dispatch and background runner
    mock_dispatch = AsyncMock(return_value=MagicMock(status="queued", inputs={"messages": []}))
    mock_run = AsyncMock()

    with patch("app.core.engine.event.handlers.a2a.dispatch_agent_run", mock_dispatch), \
         patch("app.core.engine.event.handlers.a2a.run_agent_background", mock_run):
        
        await subscriber._handle_a2a_task(cmd)

        # Check database Conversation addition
        assert mock_session.add.call_count > 0
        added_objs = [call[0][0] for call in mock_session.add.call_args_list]
        assert any(isinstance(obj, Conversation) and obj.id == task_id for obj in added_objs)

        # Verify agent run dispatched
        mock_dispatch.assert_called_once()
        mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_complete_task_tool(mock_session):
    """Verify CompleteTaskTool uploads output files and sends callback."""
    worker_thread_id = f"worker-{uuid.uuid4().hex[:8]}"
    parent_thread_id = f"parent-{uuid.uuid4().hex[:8]}"

    ctx = EvoContext(thread_id=worker_thread_id, project_id=DEFAULT_PROJECT_ID, run_id="run-2")
    ContextManager.set(ctx)

    # Set up mock DB returns (return a worker conversation)
    mock_conv = Conversation(
        id=worker_thread_id,
        project_id=DEFAULT_PROJECT_ID,
        title="Worker subtask",
        parent_thread_id=parent_thread_id,
        caller_device_key="caller-key-123"
    )
    mock_session.get.return_value = mock_conv

    # Setup mock system message query
    mock_sys_msg = Message(
        id=f"msg-{uuid.uuid4().hex[:8]}",
        thread_id=worker_thread_id,
        role="system",
        content="initiated by device key: caller-key-123",
        sequence_number=1
    )
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = mock_sys_msg
    mock_session.execute.return_value = res_mock

    mock_upload = AsyncMock(return_value={
        "filename": "output.tar",
        "download_url": "http://mock/output.tar",
        "file_size": 200,
        "md5": "xyz"
    })
    mock_send = AsyncMock()  # Must be AsyncMock because it is awaited!

    # We mock activity_monitor.end_run to prevent background state updates
    with patch.object(evocloud_manager.api, "upload_file", mock_upload), \
         patch.object(evocloud_manager.api, "send_command_to_device", mock_send), \
         patch("app.core.monitoring.activity.activity_monitor.end_run", AsyncMock()):
        
        # We call the underlying coroutine to bypass LangChain's exception handler decorator
        with pytest.raises(AgentCancelledException):
            await complete_task.coroutine(
                status="success",
                summary="Build completed successfully",
                attachments=["/mock/output.tar"]
            )

        # Check callback command sent
        assert mock_send.call_count == 1
        call_args = mock_send.call_args[1]
        assert call_args["device_key"] == "caller-key-123"
        
        cmd_payload = call_args["cmd_data"]
        assert cmd_payload["action"] == "a2a_callback"
        callback_data = cmd_payload["content"]
        assert callback_data["status"] == "success"
        assert callback_data["summary"] == "Build completed successfully"
        assert len(callback_data["attachments"]) == 1
        assert callback_data["attachments"][0]["filename"] == "output.tar"


@pytest.mark.asyncio
async def test_send_agent_task_tool_hop_count_limit(mock_session):
    """Verify SendAgentTaskTool returns error when depth exceeds 3 hops."""
    thread_id = "thread-4"
    ctx = EvoContext(thread_id=thread_id, project_id=DEFAULT_PROJECT_ID, run_id="run-1")
    ContextManager.set(ctx)

    # Set up mock DB returns for recursive parent chain traversal
    mock_conversations = {
        "thread-4": Conversation(id="thread-4", parent_thread_id="thread-3", root_thread_id="thread-1"),
        "thread-3": Conversation(id="thread-3", parent_thread_id="thread-2", root_thread_id="thread-1"),
        "thread-2": Conversation(id="thread-2", parent_thread_id="thread-1", root_thread_id="thread-1"),
        "thread-1": Conversation(id="thread-1", parent_thread_id=None, root_thread_id=None),
    }

    async def mock_get(model, ident):
        if model == Conversation:
            return mock_conversations.get(ident)
        return None
    mock_session.get.side_effect = mock_get

    res = await send_agent_task.coroutine(
        target_device_key="worker-key",
        instruction="Nested task that exceeds limit",
        attachments=[]
    )
    assert "Maximum chain delegation depth (3 hops) exceeded" in res


@pytest.mark.asyncio
async def test_handle_a2a_task_hop_count_limit():
    """Verify receiver rejects task with hop count exceeding limit."""
    task_id = "task-hop-limit"
    task_envelope = AgentTask(
        task_id=task_id,
        instruction="Too deep",
        caller_role="desktop",
        global_goal="Run nested tasks",
        attachments=[],
        caller_device_key="caller-key",
        root_thread_id="root-123",
        parent_thread_id="parent-123",
        hop_count=4,  # Over the limit of 3
        max_hops=3
    )

    cmd = RemoteCommand(
        action="a2a_task",
        content=task_envelope.model_dump(),
        thread_id=task_id,
        project_id=DEFAULT_PROJECT_ID
    )

    subscriber = A2ACommandHandler()
    mock_send_error = AsyncMock()

    with patch.object(subscriber, "_send_a2a_error", mock_send_error):
        await subscriber._handle_a2a_task(cmd)
        mock_send_error.assert_called_once()
        called_task = mock_send_error.call_args[0][0]
        called_error = mock_send_error.call_args[0][1]
        assert called_task.task_id == task_id
        assert "Maximum chain delegation depth exceeded" in called_error


@pytest.mark.asyncio
async def test_handle_a2a_task_file_download_and_verify(mock_session, tmp_path):
    """Verify receiver downloads attachments and checks MD5 validation."""
    task_id = "task-file-download"
    
    # MD5 of b"hello world" is 5eb63bbbe01eeed093cb22bb8f5acdc3
    task_envelope = AgentTask(
        task_id=task_id,
        instruction="Download and read",
        caller_role="desktop",
        global_goal="Process files",
        attachments=[
            TaskAttachment(
                filename="test.txt",
                download_url="http://mock/test.txt",
                file_size=11,
                md5="5eb63bbbe01eeed093cb22bb8f5acdc3"
            )
        ],
        caller_device_key="caller-key",
        root_thread_id="root-123",
        parent_thread_id="parent-123",
        hop_count=1,
        max_hops=3
    )

    cmd = RemoteCommand(
        action="a2a_task",
        content=task_envelope.model_dump(),
        thread_id=task_id,
        project_id=DEFAULT_PROJECT_ID
    )

    # Mock httpx client streaming hello world
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    
    async def mock_aiter():
        yield b"hello world"
    mock_response.aiter_bytes = mock_aiter

    from contextlib import asynccontextmanager
    class MockAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        
        @asynccontextmanager
        async def stream(self, method, url, **kwargs):
            yield mock_response

    subscriber = A2ACommandHandler()
    mock_dispatch = AsyncMock(return_value=MagicMock(status="queued", inputs={"messages": []}))
    mock_run = AsyncMock()
    mock_send = AsyncMock()

    with patch.object(settings, "EVOLOOP_APP_DATA_DIR", str(tmp_path)), \
         patch("httpx.AsyncClient", return_value=MockAsyncClient()), \
         patch.object(evocloud_manager.api, "send_command_to_device", mock_send), \
         patch("app.core.engine.event.handlers.a2a.dispatch_agent_run", mock_dispatch), \
         patch("app.core.engine.event.handlers.a2a.run_agent_background", mock_run):
        
        await subscriber._handle_a2a_task(cmd)
        
        # Verify it downloaded the file and dispatched successfully
        mock_dispatch.assert_called_once()
        mock_run.assert_called_once()

    # Now verify MD5 mismatch scenario
    task_envelope_bad = task_envelope.model_copy(update={
        "attachments": [
            TaskAttachment(
                filename="test.txt",
                download_url="http://mock/test.txt",
                file_size=11,
                md5="wrong_md5_hash"
            )
        ]
    })
    cmd_bad = RemoteCommand(
        action="a2a_task",
        content=task_envelope_bad.model_dump(),
        thread_id=task_id,
        project_id=DEFAULT_PROJECT_ID
    )

    mock_send_error = AsyncMock()
    with patch.object(settings, "EVOLOOP_APP_DATA_DIR", str(tmp_path)), \
         patch("httpx.AsyncClient", return_value=MockAsyncClient()), \
         patch.object(evocloud_manager.api, "send_command_to_device", mock_send), \
         patch.object(subscriber, "_send_a2a_error", mock_send_error):
        
        await subscriber._handle_a2a_task(cmd_bad)
        mock_send_error.assert_called_once()
        assert "Attachment MD5 mismatch" in mock_send_error.call_args[0][1]


@pytest.mark.asyncio
async def test_complete_task_cancelled(mock_session):
    """Verify CompleteTaskTool supports cancelled status callback."""
    worker_thread_id = f"worker-{uuid.uuid4().hex[:8]}"
    parent_thread_id = f"parent-{uuid.uuid4().hex[:8]}"

    ctx = EvoContext(thread_id=worker_thread_id, project_id=DEFAULT_PROJECT_ID, run_id="run-2")
    ContextManager.set(ctx)

    mock_conv = Conversation(
        id=worker_thread_id,
        project_id=DEFAULT_PROJECT_ID,
        title="Worker subtask",
        parent_thread_id=parent_thread_id,
        caller_device_key="caller-key-123"
    )
    mock_session.get.return_value = mock_conv

    mock_sys_msg = Message(
        id=f"msg-{uuid.uuid4().hex[:8]}",
        thread_id=worker_thread_id,
        role="system",
        content="initiated by device key: caller-key-123",
        sequence_number=1
    )
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = mock_sys_msg
    mock_session.execute.return_value = res_mock

    mock_send = AsyncMock()

    with patch.object(evocloud_manager.api, "send_command_to_device", mock_send), \
         patch("app.core.monitoring.activity.activity_monitor.end_run", AsyncMock()):
        
        with pytest.raises(AgentCancelledException):
            await complete_task.coroutine(
                status="cancelled",
                summary="Cancelled by human",
                attachments=[]
            )

        assert mock_send.call_count == 1
        call_args = mock_send.call_args[1]
        assert call_args["device_key"] == "caller-key-123"
        callback_data = call_args["cmd_data"]["content"]
        assert callback_data["status"] == "cancelled"
        assert callback_data["summary"] == "Cancelled by human"


@pytest.mark.asyncio
async def test_handle_stop_command():
    """Verify subscriber handles stop command and cancels the run."""
    thread_id = "thread-to-stop"
    cmd = RemoteCommand(
        action="stop",
        payload={},
        thread_id=thread_id,
        project_id=DEFAULT_PROJECT_ID
    )

    subscriber = EngineCommandSubscriber()
    mock_stop_run = AsyncMock()

    with patch("app.core.monitoring.activity.activity_monitor.stop_run", mock_stop_run):
        await subscriber._handle_stop(cmd)
        mock_stop_run.assert_called_once_with(thread_id)


@pytest.mark.asyncio
async def test_list_conversations_filters_sub_threads(mock_session):
    """Verify list_conversations API filters out sub-conversations (where parent_thread_id is not null)."""
    from app.api.routes.conversations import list_conversations
    
    # 1. Mock Conversation database records
    c1 = Conversation(id="conv-1", title="Root thread 1", project_id=1, parent_thread_id=None, is_pinned=False)
    c2 = Conversation(id="conv-2", title="Root thread 2", project_id=1, parent_thread_id=None, is_pinned=False)
    
    # Setup mock executes
    mock_execute_res = MagicMock()
    mock_execute_res.scalar.return_value = 2  # Total count for root threads
    mock_execute_res.scalars.return_value.all.return_value = [c1, c2]
    mock_session.execute.return_value = mock_execute_res

    # 2. Patch session_scope to return our mock session
    @asynccontextmanager
    async def mock_session_scope():
        yield mock_session

    with patch("app.api.routes.conversations.session_scope", mock_session_scope), \
         patch("app.core.monitoring.activity.activity_monitor.get_statuses", AsyncMock(return_value={})):
        
        response = await list_conversations(project_id=1)
        
        # Verify response structure and data
        assert response.success is True
        assert len(response.data) == 2
        assert response.data[0].thread_id == "conv-1"
        assert response.data[1].thread_id == "conv-2"
        
        # Verify SQL queries include the parent_thread_id is None filter
        assert mock_session.execute.call_count == 2
        calls = mock_session.execute.call_args_list
        
        # First call: count total
        count_query = str(calls[0][0][0])
        assert "parent_thread_id IS NULL" in count_query or "parent_thread_id is null" in count_query.lower()
        
        # Second call: paginated fetch
        fetch_query = str(calls[1][0][0])
        assert "parent_thread_id IS NULL" in fetch_query or "parent_thread_id is null" in fetch_query.lower()


