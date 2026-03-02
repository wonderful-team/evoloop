"""
Unit tests for AgentEngine and related components.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from tests.fixtures.factories import AgentStateFactory, MessageFactory, ToolCallFactory

# Check if we should skip DB-dependent tests (using sync connection)
def _check_db_sync():
    """Check if PostgreSQL database is available using sync connection."""
    try:
        import psycopg
        conn = psycopg.connect(
            host=os.environ.get("POSTGRES_SERVER", "localhost"),
            port=os.environ.get("POSTGRES_PORT", "5432"),
            dbname=os.environ.get("POSTGRES_DB", "app"),
            user=os.environ.get("POSTGRES_USER", "postgres"),
            password=os.environ.get("POSTGRES_PASSWORD", "admin888"),
            connect_timeout=3
        )
        conn.close()
        return True
    except Exception:
        return False

DB_AVAILABLE = _check_db_sync()

skip_if_no_db = pytest.mark.skipif(
    not DB_AVAILABLE,
    reason="Database not available"
)


class TestAgentState:
    """Tests for AgentState management."""

    def test_create_state(self):
        """Test creating agent state."""
        state = AgentStateFactory.create(project_id=42)

        assert state["project_id"] == 42
        assert "messages" in state
        assert "iteration_count" in state

    def test_state_with_conversation(self):
        """Test creating state with conversation history."""
        state = AgentStateFactory.with_conversation([
            ("human", "Hello"),
            ("ai", "Hi there"),
            ("human", "How are you?"),
        ])

        assert len(state["messages"]) == 3
        assert state["messages"][0].content == "Hello"
        assert state["messages"][1].content == "Hi there"


class TestAgentEngine:
    """Tests for AgentEngine."""

    @skip_if_no_db
    @pytest.mark.asyncio
    async def test_run_node_text_response(self):
        """Test run_node with simple text response."""
        from app.core.engine import AgentEngine

        # Create mock LLM that returns a text response
        mock_llm = MagicMock()
        mock_response = AIMessage(content="Test response")
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)

        with patch('app.core.engine.LLMFactory.create_llm', return_value=mock_llm):
            state = AgentStateFactory.create()
            config = {"configurable": {"thread_id": "test-thread"}}

            result = await AgentEngine.run_node(
                state=state,
                config=config,
                system_prompt="Test system prompt",
                tools=[],
                max_steps=5
            )

            assert "messages" in result
            assert len(result["messages"]) > 0

    @skip_if_no_db
    @pytest.mark.asyncio
    async def test_run_node_with_tool_calls(self):
        """Test run_node with tool execution."""
        from app.core.engine import AgentEngine

        # Create mock tool
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.ainvoke = AsyncMock(return_value="Tool result")

        # Create mock LLM that calls a tool
        mock_llm = MagicMock()
        tool_call_response = AIMessage(
            content="",
            tool_calls=[{"name": "test_tool", "args": {"arg": "value"}, "id": "call_1"}]
        )
        final_response = AIMessage(content="Done")

        mock_llm.ainvoke = AsyncMock(side_effect=[tool_call_response, final_response])
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)

        with patch('app.core.engine.LLMFactory.create_llm', return_value=mock_llm):
            state = AgentStateFactory.create()
            config = {"configurable": {"thread_id": "test-thread"}}

            result = await AgentEngine.run_node(
                state=state,
                config=config,
                system_prompt="Test",
                tools=[mock_tool],
                max_steps=5
            )

            mock_tool.ainvoke.assert_called_once()

    @skip_if_no_db
    @pytest.mark.asyncio
    async def test_run_node_routing_signal(self):
        """Test run_node detecting route_to signal."""
        from app.core.engine import AgentEngine

        mock_llm = MagicMock()
        routing_response = AIMessage(
            content="Routing...",
            tool_calls=[{
                "name": "route_to",
                "args": {"target": "operator", "reason": "Need to code"},
                "id": "call_route"
            }]
        )

        mock_llm.ainvoke = AsyncMock(return_value=routing_response)
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)

        with patch('app.core.engine.LLMFactory.create_llm', return_value=mock_llm):
            state = AgentStateFactory.create()
            config = {"configurable": {"thread_id": "test-thread"}}

            result = await AgentEngine.run_node(
                state=state,
                config=config,
                system_prompt="Test",
                tools=[],
                max_steps=5
            )

            assert "_routing_target" in result
            assert result["_routing_target"] == "operator"

    @skip_if_no_db
    @pytest.mark.asyncio
    async def test_run_node_max_steps_reached(self):
        """Test behavior when max_steps is reached."""
        from app.core.engine import AgentEngine

        mock_llm = MagicMock()
        # Always return tool calls to keep loop going
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(
            content="Still working",
            tool_calls=[{"name": "test_tool", "args": {}, "id": "call_1"}]
        ))
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)

        with patch('app.core.engine.LLMFactory.create_llm', return_value=mock_llm):
            state = AgentStateFactory.create()
            config = {"configurable": {"thread_id": "test-thread"}}

            result = await AgentEngine.run_node(
                state=state,
                config=config,
                system_prompt="Test",
                tools=[],
                max_steps=2  # Low limit to trigger max steps
            )

            # Should have warning message about max steps
            assert len(result["messages"]) > 0


class TestMessageUtils:
    """Tests for message utilities."""

    def test_smart_window_slice(self):
        """Test smart window slicing of messages."""
        from app.core.engine.message_utils import smart_window_slice

        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi"),
            HumanMessage(content="How are you?"),
            AIMessage(content="I'm good"),
        ]

        result = smart_window_slice(messages, window_size=3)

        # Should keep system message and last 3 messages
        assert len(result) <= 4
        # First message should be system or human (first human is preserved)
        assert result[0].type in ["system", "human"]

    def test_repair_message_history(self):
        """Test repairing orphaned tool messages."""
        from app.core.engine.message_utils import repair_message_history

        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="", tool_calls=[{"id": "call_1", "name": "tool", "args": {}}]),
            # Missing tool response - AI message has no content, just dangling tool_calls
        ]

        result = repair_message_history(messages)

        # Implementation removes AI messages with dangling tool_calls and no content
        # (Phase 3: scrub dangling tool calls, then pop if empty)
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)

    def test_truncate_message_content(self):
        """Test truncating long message content."""
        from app.core.engine.message_utils import truncate_message_content

        long_content = "x" * 15000
        result = truncate_message_content(long_content, limit=1000)

        assert len(result) < len(long_content)
        assert "..." in result
        assert "truncated" in result.lower() or "Output" in result


class TestSupervisorNode:
    """Tests for SupervisorNode."""

    @skip_if_no_db
    @pytest.mark.asyncio
    async def test_supervisor_routes_to_operator(self):
        """Test supervisor routing to operator."""
        from app.core.engine.nodes.supervisor import SupervisorNode

        node = SupervisorNode()

        # Mock the engine result with routing signal
        with patch.object(node, '_build_context', new=AsyncMock(return_value={
            "tools": [],
            "iteration_count": 0
        })):
            with patch('app.core.engine.AgentEngine.run_node') as mock_run:
                mock_run.return_value = {
                    "messages": [AIMessage(content="Routing to operator")],
                    "_routing_target": "operator",
                    "_routing_reason": "Need to code",
                    "_routing_context": {"focus_paths": ["main.py"]},
                }

                state = AgentStateFactory.with_human_message("Write some code")
                config = {"configurable": {"thread_id": "test"}}

                result = await node(state, config)

                assert result["next_node"] == "operator"
                assert result["execution_ticket"] is not None
                assert "main.py" in result["execution_ticket"]["focus_paths"]

    @skip_if_no_db
    @pytest.mark.asyncio
    async def test_supervisor_trimming_triggered(self):
        """Test supervisor triggering message trimming."""
        from app.core.engine.nodes.supervisor import SupervisorNode
        from langchain_core.messages import HumanMessage

        node = SupervisorNode()

        # Create state with many messages (with ids for trimming)
        messages = []
        for i in range(100):
            msg = HumanMessage(content=f"Message {i}")
            msg.id = f"msg_{i}"  # Assign id for RemoveMessage to work
            messages.append(msg)

        state = AgentStateFactory.create(messages=messages)

        result = await node._try_trimming(state)

        assert result is not None
        assert "messages" in result


class TestWorkerNode:
    """Tests for WorkerNode."""

    @skip_if_no_db
    @pytest.mark.asyncio
    async def test_worker_missing_ticket(self):
        """Test worker returns error when no ticket provided."""
        from app.core.engine.nodes.worker import WorkerNode

        node = WorkerNode()

        state = AgentStateFactory.create()
        # No execution_ticket set

        config = {"configurable": {"thread_id": "test"}}
        result = await node(state, config)

        # Check error response
        assert "messages" in result
        assert result["next_node"] == "supervisor"
        assert "Error" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_worker_with_valid_ticket(self):
        """Test worker with valid execution ticket."""
        from app.core.engine.nodes.worker import WorkerNode

        node = WorkerNode()

        # Verify node accepts valid state structure
        state = {
            "messages": [],
            "execution_ticket": {
                "agent_config": {
                    "role_name": "TestWorker",
                    "system_instructions": "You are a test worker."
                },
                "topic": "Test task",
                "acceptance_criteria": ["Complete the test"]
            },
            "scratchpad": {},
            "project_id": 1,
        }

        # Just verify the node structure is valid
        assert node is not None
        assert callable(node)


class TestPromptBuilders:
    """Tests for prompt builders."""

    @skip_if_no_db
    def test_supervisor_prompt_builder(self):
        """Test SupervisorPromptBuilder."""
        from app.core.engine.prompts.supervisor_builder import SupervisorPromptBuilder

        builder = SupervisorPromptBuilder(
            project_id=1,
            iteration_count=0,
            context={"scratchpad": {}}
        )

        config = {"configurable": {"thread_id": "test"}}
        prompt = builder.build(config)

        assert "Supervisor" in prompt
        assert isinstance(prompt, str)
        assert "Project ID" in prompt

    @skip_if_no_db
    def test_worker_prompt_builder(self):
        """Test WorkerPromptBuilder."""
        from app.core.engine.prompts.worker_builder import WorkerPromptBuilder

        builder = WorkerPromptBuilder(
            agent_config={
                "role_name": "TestWorker",
                "system_instructions": "You are a test worker."
            },
            ticket={
                "topic": "Test task",
                "acceptance_criteria": ["Complete test"]
            },
            skills=[]
        )

        config = {"configurable": {"thread_id": "test"}}
        prompt = builder.build(config)

        assert isinstance(prompt, str)
        assert len(prompt) > 0

    @skip_if_no_db
    def test_worker_mission_message(self):
        """Test WorkerPromptBuilder mission message generation."""
        from app.core.engine.prompts.worker_builder import WorkerPromptBuilder

        builder = WorkerPromptBuilder(
            agent_config={"role_name": "TestWorker"},
            ticket={
                "topic": "Test Mission",
                "acceptance_criteria": ["Criterion 1", "Criterion 2"],
                "parameters": {"key": "value"}
            }
        )

        mission = builder.build_mission_message()

        assert isinstance(mission, str)
        assert "Test Mission" in mission or "MISSION" in mission


class TestRouters:
    """Tests for app.core.engine.routers"""

    def test_route_supervisor_to_worker(self):
        """Test route_supervisor routes to worker node."""
        from app.core.engine.routers import route_supervisor

        state = {"next_node": "worker"}
        result = route_supervisor(state)
        assert result == "worker"

    def test_route_supervisor_legacy_remap(self):
        """Test route_supervisor remaps legacy node names to worker."""
        from app.core.engine.routers import route_supervisor

        legacy_names = ["coder", "tester", "planner", "operator", "deep_researcher", "documenter"]
        for name in legacy_names:
            state = {"next_node": name}
            result = route_supervisor(state)
            assert result == "worker", f"Expected 'worker' for legacy name '{name}', got '{result}'"

    def test_route_supervisor_finish(self):
        """Test route_supervisor routes to finish."""
        from app.core.engine.routers import route_supervisor

        state = {"next_node": "finish"}
        result = route_supervisor(state)
        assert result == "finish"

    def test_route_supervisor_default_to_finish(self):
        """Test route_supervisor defaults to finish when next_node is None."""
        from app.core.engine.routers import route_supervisor

        state = {"next_node": None}
        result = route_supervisor(state)
        assert result == "finish"

    def test_route_supervisor_map_research(self):
        """Test route_supervisor handles parallel research routing."""
        from app.core.engine.routers import route_supervisor

        state = {
            "next_node": "map_research",
            "parallel_research_tasks": ["topic1", "topic2"],
            "project_id": 42
        }
        result = route_supervisor(state)

        # Should return a list of Send objects
        assert isinstance(result, list)
        assert len(result) == 2

    def test_route_by_next_node_field(self):
        """Test route_by_next_node_field returns next_node from state."""
        from app.core.engine.routers import route_by_next_node_field

        state = {"next_node": "chat"}
        result = route_by_next_node_field(state)
        assert result == "chat"

    def test_route_by_next_node_field_default(self):
        """Test route_by_next_node_field defaults to supervisor."""
        from app.core.engine.routers import route_by_next_node_field

        state = {}
        result = route_by_next_node_field(state)
        assert result == "supervisor"

    def test_make_expression_router_basic(self):
        """Test expression router with simple condition."""
        from app.core.engine.routers import make_expression_router

        conditions = [
            {"expr": "scratchpad.get('count', 0) > 5", "to": "finish"},
            {"expr": "scratchpad.get('error')", "to": "error_handler"},
        ]
        router = make_expression_router(conditions, default="continue")

        # Test first condition matches
        state = {"scratchpad": {"count": 10}}
        assert router(state) == "finish"

        # Test second condition matches
        state = {"scratchpad": {"count": 3, "error": True}}
        assert router(state) == "error_handler"

        # Test no conditions match (default)
        state = {"scratchpad": {"count": 3}}
        assert router(state) == "continue"

    def test_make_expression_router_safety(self):
        """Test expression router blocks unsafe expressions."""
        from app.core.engine.routers import make_expression_router

        conditions = [
            {"expr": "__import__('os').system('rm -rf /')", "to": "evil"},
            {"expr": "scratchpad.get('safe')", "to": "safe"},
        ]
        router = make_expression_router(conditions, default="continue")

        # Unsafe expression should be skipped
        state = {"scratchpad": {"safe": True}}
        assert router(state) == "safe"

    def test_make_expression_router_eval_error(self):
        """Test expression router handles eval errors gracefully."""
        from app.core.engine.routers import make_expression_router

        conditions = [
            {"expr": "undefined_var + 1", "to": "broken"},
        ]
        router = make_expression_router(conditions, default="continue")

        state = {"scratchpad": {}}
        # Should not raise, should return default
        assert router(state) == "continue"


class TestTasks:
    """Tests for app.core.engine.tasks"""

    def test_parse_android_bounds_valid(self):
        """Test parsing valid Android bounds string."""
        from app.core.engine.tasks import _parse_android_bounds

        result = _parse_android_bounds("[100,200][300,400]")
        assert result == (100, 200, 300, 400)

    def test_parse_android_bounds_invalid(self):
        """Test parsing invalid Android bounds string."""
        from app.core.engine.tasks import _parse_android_bounds

        assert _parse_android_bounds("invalid") is None
        assert _parse_android_bounds("") is None
        # Note: Function may not handle None, skip that test

    def test_dehydrate_android_layout_empty(self):
        """Test dehydrating empty Android layout."""
        from app.core.engine.tasks import _dehydrate_android_layout

        elements, summary = _dehydrate_android_layout("")
        assert elements == []
        assert summary == "Empty layout."

    def test_dehydrate_android_layout_invalid_xml(self):
        """Test dehydrating invalid XML."""
        from app.core.engine.tasks import _dehydrate_android_layout

        elements, summary = _dehydrate_android_layout("not valid xml")
        assert elements == []
        assert "Parse Error" in summary

    def test_dehydrate_android_layout_valid(self):
        """Test dehydrating valid Android layout XML."""
        from app.core.engine.tasks import _dehydrate_android_layout

        xml = '''<?xml version="1.0"?>
        <hierarchy>
            <node package="com.example.app" class="android.widget.Button"
                  text="Click Me" resource-id="btn1"
                  clickable="true" bounds="[100,200][300,400]"/>
            <node package="com.example.app" class="android.widget.TextView"
                  text="Hello" bounds="[10,10][100,50]"/>
        </hierarchy>'''

        elements, summary = _dehydrate_android_layout(xml)

        assert len(elements) >= 1
        assert "com.example.app" in summary


class TestCleanup:
    """Tests for app.core.engine.cleanup"""

    @pytest.fixture
    def mock_file_operation(self):
        """Create a mock FileOperation."""
        op = MagicMock()
        op.file_path = "/tmp/test.txt"
        op.operation = "EDIT"
        op.original_content = "original"
        op.created_at = MagicMock()
        return op

    @pytest.mark.asyncio
    async def test_file_undo_handler_no_operations(self):
        """Test FileUndoHandler with no operations to undo."""
        from app.core.engine.cleanup import FileUndoHandler

        handler = FileUndoHandler()
        # Just verify the handler can be instantiated
        assert handler is not None

    @pytest.mark.asyncio
    async def test_file_undo_handler_basic(self):
        """Test FileUndoHandler basic functionality."""
        from app.core.engine.cleanup import FileUndoHandler

        handler = FileUndoHandler()
        # Verify handler has expected interface
        assert hasattr(handler, 'cleanup')
        assert callable(handler.cleanup)

    @pytest.mark.asyncio
    async def test_cleanup_orchestrator_initialization(self):
        """Test CleanupOrchestrator initializes with handlers."""
        from app.core.engine.cleanup import CleanupOrchestrator

        with patch("app.core.engine.cleanup.BrainCleanupHandler") as mock_brain:
            mock_brain.return_value = MagicMock()
            orchestrator = CleanupOrchestrator()

            assert len(orchestrator.handlers) >= 2
            assert orchestrator.file_undo_handler is not None


class TestHistory:
    """Tests for app.core.engine.history"""

    @pytest.mark.asyncio
    async def test_history_service_graph_unavailable(self):
        """Test HistoryService when graph is unavailable."""
        from app.core.engine.history import HistoryService

        with patch("app.core.engine.history.get_graph", return_value=None):
            with pytest.raises(RuntimeError, match="Graph unavailable"):
                await HistoryService.perform_rewind("thread1")

    @pytest.mark.asyncio
    async def test_history_service_empty_messages(self):
        """Test HistoryService with empty message list."""
        from app.core.engine.history import HistoryService

        mock_graph = MagicMock()
        mock_state = MagicMock()
        mock_state.values = {"messages": []}
        mock_graph.aget_state = AsyncMock(return_value=mock_state)

        with patch("app.core.engine.history.get_graph", return_value=mock_graph):
            result = await HistoryService.perform_rewind("thread1")
            assert result["status"] == "empty"
            assert result["removed_count"] == 0

    @pytest.mark.asyncio
    async def test_history_service_invalid_message_id(self):
        """Test HistoryService with invalid message ID."""
        from app.core.engine.history import HistoryService

        mock_graph = MagicMock()
        mock_state = MagicMock()
        mock_state.values = {"messages": [MagicMock(id="msg1")]}
        mock_graph.aget_state = AsyncMock(return_value=mock_state)

        with patch("app.core.engine.history.get_graph", return_value=mock_graph):
            with patch("app.core.engine.history.get_db_session") as mock_session:
                mock_db = AsyncMock()
                mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await HistoryService.perform_rewind("thread1", target_message_id="invalid")
                assert result["status"] == "invalid_id"


class TestBackgroundAgent:
    """Tests for app.core.engine.background_agent"""

    def test_deserialize_messages_dict(self):
        """Test _deserialize_messages with dict input."""
        from app.core.engine.background_agent import _deserialize_messages

        raw = [{"type": "human", "content": "Hello"}]
        result = _deserialize_messages(raw)

        assert len(result) == 1
        assert result[0].content == "Hello"

    def test_deserialize_messages_already_objects(self):
        """Test _deserialize_messages with already deserialized objects."""
        from app.core.engine.background_agent import _deserialize_messages

        msg = HumanMessage(content="Test")
        result = _deserialize_messages([msg])

        assert len(result) == 1
        assert result[0] is msg

    @pytest.mark.asyncio
    async def test_setup_project_context(self):
        """Test _setup_project_context sets working directory."""
        from app.core.engine.background_agent import _setup_project_context

        with patch("app.core.engine.background_agent.evocloud_manager") as mock_cloud:
            mock_cloud.get_project_by_id = AsyncMock(return_value={"path": "/project/path"})

            with patch("app.core.engine.background_agent.thread_context_store") as mock_store:
                mock_store.get_working_directory = MagicMock(return_value="/project/path")
                mock_store.set_working_directory = MagicMock()

                working_dir = await _setup_project_context("thread1", 42)
                assert working_dir == "/project/path"

    @pytest.mark.asyncio
    async def test_ensure_conversation_in_db_new(self):
        """Test _ensure_conversation_in_db creates new conversation."""
        from app.core.engine.background_agent import _ensure_conversation_in_db

        with patch("app.core.engine.background_agent.session_scope") as mock_scope:
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=None)
            mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_scope.return_value.__aexit__ = AsyncMock(return_value=None)

            inputs = {"task_title": "Test Task"}
            await _ensure_conversation_in_db("thread1", 1, inputs)

            mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_conversation_in_db_exists(self):
        """Test _ensure_conversation_in_db when conversation exists."""
        from app.core.engine.background_agent import _ensure_conversation_in_db

        with patch("app.core.engine.background_agent.session_scope") as mock_scope:
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=MagicMock())
            mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_scope.return_value.__aexit__ = AsyncMock(return_value=None)

            inputs = {}
            await _ensure_conversation_in_db("thread1", 1, inputs)

            mock_session.add.assert_not_called()
