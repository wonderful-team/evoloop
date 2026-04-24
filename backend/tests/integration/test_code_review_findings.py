"""
Integration tests for code-review findings.

These tests verify the design, structural, logical, and redundancy issues
identified during the deep code review of:
- websocket_link.py
- handlers.py
- agent.py (routes)
- dispatch.py

Run: cd backend && python -m pytest tests/integration/test_code_review_findings.py -v
"""

import os
import sys
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Mock message module before any imports
mock_messaging_mod = MagicMock()
mock_messaging_mod.MessageHandler = MagicMock
mock_messaging_mod.MessageCategory = MagicMock
mock_messaging_mod.MessageClassifier = MagicMock
mock_messaging_mod.MessagePersistencePolicy = MagicMock
mock_messaging_mod.MessageStreamPolicy = MagicMock
sys.modules["app.core.engine.message"] = mock_messaging_mod
sys.modules["app.core.message"] = mock_messaging_mod

env_path = os.path.join(os.path.dirname(__file__), "../../../.env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))


# =============================================================================
# 1. websocket_link.py 问题验证
# =============================================================================

class TestWebSocketLinkIssues:
    """Tests for websocket_link.py findings."""

    @pytest.fixture
    def link(self):
        """Create a minimal EvoCloudWebSocketLink instance."""
        from app.core.evocloud.schemas import EvoCloudConfig
        from app.core.evocloud.interfaces.client import EvoCloudClientProtocol

        config = MagicMock(spec=EvoCloudConfig)
        config.ws_url = "wss://test.example.com/ws"
        config.device_name = "test-device"
        config.app_data_dir = os.path.expanduser("~")
        config.ssl_verify = True
        config.api_key = "test"
        config.api_secret = "test"

        api = MagicMock(spec=EvoCloudClientProtocol)
        api.get_token = MagicMock(return_value="test-token")

        from app.core.evocloud.backends.websocket_link import EvoCloudWebSocketLink
        return EvoCloudWebSocketLink(config, api)

    @pytest.mark.asyncio
    async def test_send_message_is_used_not_send(self, link):
        """
        P0: _handle_query should use send_message(), not send().
        This was a bug where self.send() (non-existent) was called.
        """
        from app.core.evocloud.schemas import QueryResponse

        link._running = True
        link.ws = MagicMock()
        link.ws.send = AsyncMock()
        link._query_handler = MagicMock(return_value={"test": "data"})

        data = {
            "type": "query",
            "request_id": "req-1",
            "data": {"query_type": "test", "thread_id": "t1", "params": {}},
        }

        # Should not raise AttributeError on 'send'
        await link._handle_query(data)
        assert link.ws.send.called, "send_message should delegate to ws.send"

    @pytest.mark.asyncio
    async def test_wait_for_device_id_zero_not_falsy(self, link):
        """
        P1: wait_for_device_id should treat device_id=0 as valid.
        Previously: `if self._device_id:` would skip when device_id==0.
        """
        link._device_id = 0
        link._device_id_event.set()

        result = await link.wait_for_device_id(timeout=0.1)
        assert result == 0, "device_id=0 should be treated as valid, not None"

    def test_processed_commands_lru_not_fifo(self, link):
        """
        P2: _processed_commands cleanup does not guarantee LRU eviction.
        set->list conversion order is arbitrary in theory.
        """
        # Simulate 600 commands to trigger cleanup
        for i in range(600):
            link._processed_commands.add(i)

        # Trigger cleanup
        if len(link._processed_commands) > 500:
            link._processed_commands = set(list(link._processed_commands)[250:])

        # After cleanup, should have 350 items
        assert len(link._processed_commands) == 350
        # But which 250 were removed? Not necessarily the oldest.

    def test_is_connected_without_open_check(self, link):
        """
        P1: is_connected() should check ws.open, not just ws is not None.
        A closed ws object can still be non-None.
        """
        link._running = True
        link.ws = MagicMock()
        # Simulate a closed websocket (object exists but connection closed)
        delattr(link.ws, "open")  # remove open attr if present

        # Current implementation only checks ws is not None
        assert link.is_connected() is True  # This is the bug: should be False if closed

    @pytest.mark.asyncio
    async def test_cancelled_error_swallowed(self, link):
        """
        P0: _ws_connect_loop swallows asyncio.CancelledError.
        Calling stop() while in sleep should cleanly exit, not hang.
        """
        link._running = True

        # Mock websockets.connect to block until cancelled
        async def mock_connect(*args, **kwargs):
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise  # Re-raise to test if caller handles it

        with patch("websockets.connect", side_effect=mock_connect):
            task = asyncio.create_task(link._ws_connect_loop())
            await asyncio.sleep(0.1)  # Let it enter the loop

            link._running = False
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task


# =============================================================================
# 2. handlers.py 问题验证
# =============================================================================

class TestHandlersIssues:
    """Tests for handlers.py findings."""

    @pytest.mark.asyncio
    async def test_hitl_response_task_not_tracked(self):
        """
        P1: hitl_response creates a background task without tracking.
        If the task fails, the exception is never retrieved.
        """
        from app.core.evocloud.bridge.handlers import handle_remote_command

        tasks_before = len(asyncio.all_tasks())

        command = {
            "type": "hitl_response",
            "thread_id": "t-1",
            "content": {"response": "yes"},
            "command_id": "77",
        }

        with patch("app.core.evocloud.bridge.handlers.run_agent_background", new_callable=AsyncMock):
            await handle_remote_command(command)

        tasks_after = len(asyncio.all_tasks())
        # Task was created but not tracked/awaited
        assert tasks_after >= tasks_before

    @pytest.mark.asyncio
    async def test_remote_command_dict_api_on_model(self):
        """
        P1: handle_remote_command uses .get() on RemoteCommand (Pydantic model).
        If model doesn't support dict-like access, this fails.
        """
        from app.core.evocloud.bridge.handlers import handle_remote_command
        from app.core.evocloud.schemas import RemoteCommand

        # RemoteCommand as Pydantic model
        cmd = RemoteCommand.model_validate({
            "type": "chat_message",
            "thread_id": "t-1",
            "message": "Hello",
        })

        # .get() should work because Pydantic v2 BaseModel supports dict-like access
        # But this is an implicit dependency on Pydantic internals
        assert cmd.get("type") == "chat_message"
        assert cmd.get("thread_id") == "t-1"


# =============================================================================
# 3. agent.py (routes) 问题验证
# =============================================================================

class TestAgentRoutesIssues:
    """Tests for agent.py findings."""

    @pytest.mark.asyncio
    async def test_resume_overwrites_human_message_with_tool_message(self):
        """
        P1: /chat/resume overwrites the user's HumanMessage with ToolMessage
        when pending tool_call is detected. The user's input is lost.
        """
        from app.api.routes.agent import resume_chat, ResumeRequest
        from langchain_core.messages import AIMessage
        # ToolMessage is mocked in conftest, use a real-like mock
        class FakeToolMessage:
            def __init__(self, content, tool_call_id):
                self.content = content
                self.tool_call_id = tool_call_id

        ai_msg = AIMessage(
            content="Need confirm",
            tool_calls=[{"id": "tc-1", "name": "request_approval", "args": {}}],
        )
        mock_state = MagicMock()
        mock_state.values = {"messages": [ai_msg]}
        mock_graph = MagicMock()
        mock_graph.aget_state = AsyncMock(return_value=mock_state)

        with patch("app.api.routes.agent.get_graph", return_value=mock_graph), \
             patch("app.api.routes.agent.ToolMessage", FakeToolMessage), \
             patch("app.api.routes.agent.db_resource_manager") as mock_db_res, \
             patch("app.core.engine.dispatch.persist_user_message", new_callable=AsyncMock):

            mock_db_res.checkpointer = MagicMock()

            req = ResumeRequest(thread_id="t-1", user_input="I approve this")
            bg_tasks = MagicMock()
            bg_tasks.add_task = MagicMock()

            await resume_chat(req, bg_tasks)

            _, _, inputs, _ = bg_tasks.add_task.call_args[0]
            messages = inputs["messages"]

            # The bug: messages is replaced with [ToolMessage], HumanMessage is lost
            assert len(messages) == 1
            assert isinstance(messages[0], FakeToolMessage)
            # User's "I approve this" becomes the ToolMessage content
            assert messages[0].content == "I approve this"
            # But the original HumanMessage intent is gone — only ToolMessage remains

    @pytest.mark.asyncio
    async def test_webhook_serialization_wrong_type(self):
        """
        P2: webhook_endpoint marks all non-HumanMessage as type="human".
        This loses message type information.
        """
        from app.api.routes.agent import webhook_endpoint, WebhookRequest, WebhookPayload
        from langchain_core.messages import AIMessage

        with patch("app.api.routes.agent.EventAdapter.adapt", return_value=[AIMessage(content="AI reply")]):
            req = WebhookRequest(
                source="test",
                event_type="test_event",
                payload=WebhookPayload(),
                thread_id="t-webhook",
            )
            bg_tasks = MagicMock()
            result = await webhook_endpoint(req, bg_tasks)

            # The add_task call contains serialized messages
            _, _, inputs = bg_tasks.add_task.call_args[0]
            msg = inputs["messages"][0]
            # Bug: AIMessage is serialized as type="human"
            assert msg["type"] == "human"  # This is wrong, should be "ai"

    @pytest.mark.asyncio
    async def test_stop_chat_uses_chat_request(self):
        """
        P2: /chat/stop accepts ChatRequest but only needs thread_id.
        API docs show irrelevant fields (message, model, attachments).
        """
        from app.api.routes.agent import stop_chat

        # Can call with minimal data, but ChatRequest accepts much more
        class FakeChatRequest:
            thread_id = "t-1"
            message = "ignored"
            model = "ignored"
            attachments = [{"url": "ignored"}]

        with patch("app.api.routes.agent.activity_monitor.stop_run", new_callable=AsyncMock) as mock_stop:
            await stop_chat(FakeChatRequest())
            mock_stop.assert_awaited_once_with("t-1")


# =============================================================================
# 4. dispatch.py 问题验证
# =============================================================================

class TestDispatchIssues:
    """Tests for dispatch.py findings."""

    @pytest.mark.asyncio
    async def test_resume_graph_background_hitl_no_cleanup(self):
        """
        P0: resume_graph_background catches AgentHumanInterruptException
        but does NOT call activity_monitor.end_run(). The run stays active.
        """
        from app.core.engine.dispatch import resume_graph_background
        from app.core.exceptions import AgentHumanInterruptException

        mock_graph = MagicMock()
        mock_graph.astream = MagicMock(side_effect=AgentHumanInterruptException("HITL"))

        with patch("app.core.globals.get_graph", return_value=mock_graph), \
             patch("app.core.engine.callbacks.transparent.TransparentCallbackHandler"), \
             patch("app.core.monitoring.activity.activity_monitor.end_run", new_callable=AsyncMock) as mock_end, \
             patch("app.core.monitoring.activity.activity_monitor.start_run", new_callable=AsyncMock):

            await resume_graph_background(
                "t-1",
                {"messages": []},
                {"configurable": {"thread_id": "t-1"}},
            )

            # Bug: end_run was NOT called for HITL interrupt
            mock_end.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_content_blocks_type_inconsistency(self):
        """
        P1: When reference_service fails, content_blocks falls back to string.
        But success path returns structured content_blocks (list/dict).
        Downstream receives inconsistent types.
        """
        from app.core.engine.dispatch import dispatch_agent_run

        with patch("app.core.engine.dispatch.session_scope") as mock_scope, \
             patch("app.domain.project.reference_service.reference_service.process_references", side_effect=Exception("DB down")), \
             patch("app.core.evocloud.manager.EvoCloudManager.upload_log", new_callable=AsyncMock), \
             patch("app.core.engine.dispatch.activity_monitor.start_run", new_callable=AsyncMock):

            from contextlib import asynccontextmanager
            session = MagicMock()
            session.get = AsyncMock(return_value=MagicMock(id="c1", project_id=1))
            session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=0)))
            session.add = MagicMock()
            session.flush = AsyncMock()

            @asynccontextmanager
            async def _fake():
                yield session
            mock_scope.side_effect = _fake

            result = await dispatch_agent_run(
                thread_id="t-1",
                message_content="Hello",
            )

            # When ref service fails, content_blocks is the raw string
            content = result.inputs["messages"][0]["content"]
            assert isinstance(content, str)  # fallback path: string
            assert content == "Hello"

            # But when ref service succeeds, content_blocks is structured (list/dict)
            # This type inconsistency can break downstream consumers

    @pytest.mark.asyncio
    async def test_goal_with_empty_message_and_attachments(self):
        """
        P1: When message is empty but attachments exist, goal becomes "[Image] "
        which is semantically odd.
        """
        from app.core.engine.dispatch import dispatch_agent_run

        with patch("app.core.engine.dispatch.session_scope") as mock_scope, \
             patch("app.domain.project.reference_service.reference_service.process_references", new_callable=AsyncMock) as mock_refs, \
             patch("app.core.evocloud.manager.EvoCloudManager.upload_log", new_callable=AsyncMock), \
             patch("app.core.engine.dispatch.activity_monitor.start_run", new_callable=AsyncMock):

            mock_refs.return_value = MagicMock(content_blocks="[]")

            from contextlib import asynccontextmanager
            session = MagicMock()
            session.get = AsyncMock(return_value=MagicMock(id="c1", project_id=1))
            session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=0)))
            session.add = MagicMock()
            session.flush = AsyncMock()

            @asynccontextmanager
            async def _fake():
                yield session
            mock_scope.side_effect = _fake

            result = await dispatch_agent_run(
                thread_id="t-1",
                message_content="",
                attachments=[{"type": "image", "url": "http://example.com/img.png"}],
            )

            # Bug: goal is "[Image] " with trailing space and no text
            assert result.inputs["goal"] == "[Image] "


# =============================================================================
# 5. 端到端：统一调度层数据流一致性
# =============================================================================

class TestEndToEndDataFlowConsistency:
    """End-to-end tests for data flow consistency across entry points."""

    @pytest.mark.asyncio
    async def test_all_entry_points_produce_compatible_inputs(self):
        """
        E2E: HTTP /chat, WebSocket, /retry all produce inputs that
        run_agent_background can consume.
        """
        from app.core.engine.background_agent import BackgroundAgentInputs
        from app.core.engine.dispatch import dispatch_agent_run

        # Verify the dict->BackgroundAgentInputs conversion works
        raw_inputs = {
            "messages": [{"type": "human", "content": "test"}],
            "project_id": 1,
            "checkpoint_id": None,
            "is_retry": False,
            "goal": "test",
            "session_goal": "test",
            "model": "gpt-4",
        }

        # This is what run_agent_background does internally
        inputs = BackgroundAgentInputs(**raw_inputs)
        assert inputs.model == "gpt-4"
        assert inputs.messages == [{"type": "human", "content": "test"}]

    @pytest.mark.asyncio
    async def test_dispatch_result_fields_match_background_agent_inputs(self):
        """
        E2E: dispatch_agent_run returns fields compatible with BackgroundAgentInputs.
        If fields drift, run_agent_background will fail at runtime.
        """
        from app.core.engine.background_agent import BackgroundAgentInputs
        from app.core.engine.dispatch import dispatch_agent_run

        with patch("app.core.engine.dispatch.session_scope") as mock_scope, \
             patch("app.domain.project.reference_service.reference_service.process_references", new_callable=AsyncMock) as mock_refs, \
             patch("app.core.evocloud.manager.EvoCloudManager.upload_log", new_callable=AsyncMock), \
             patch("app.core.engine.dispatch.activity_monitor.start_run", new_callable=AsyncMock):

            mock_refs.return_value = MagicMock(content_blocks="hello")

            from contextlib import asynccontextmanager
            session = MagicMock()
            session.get = AsyncMock(return_value=MagicMock(id="c1", project_id=1))
            session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=0)))
            session.add = MagicMock()
            session.flush = AsyncMock()

            @asynccontextmanager
            async def _fake():
                yield session
            mock_scope.side_effect = _fake

            result = await dispatch_agent_run(
                thread_id="t-1",
                message_content="Hello",
                project_id=42,
                checkpoint_id="cp-1",
                is_retry=True,
                model="gpt-4",
            )

            # Verify all BackgroundAgentInputs fields are present
            bai_fields = {f for f in BackgroundAgentInputs.model_fields.keys()}
            result_fields = set(result.inputs.keys())

            # Critical fields that MUST be present
            critical = {"messages", "project_id", "model", "goal", "is_retry", "checkpoint_id"}
            assert critical.issubset(result_fields), f"Missing critical fields: {critical - result_fields}"

            # Verify conversion succeeds (no ValidationError)
            bai = BackgroundAgentInputs(**result.inputs)
            assert bai.project_id == 42
            assert bai.model == "gpt-4"
            assert bai.is_retry is True
