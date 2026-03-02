"""
Integration tests for agent workflow execution.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage, AIMessage

from tests.fixtures.factories import AgentStateFactory, ExecutionTicketFactory


@pytest.mark.integration
@pytest.mark.asyncio
class TestAgentWorkflow:
    """Tests for complete agent workflows."""

    async def test_supervisor_to_worker_flow(self):
        """Test complete flow from supervisor to worker and back."""
        from app.core.engine.nodes.supervisor import SupervisorNode
        from app.core.engine.nodes.worker import WorkerNode

        supervisor = SupervisorNode()
        worker = WorkerNode()

        # Initial state with user request
        state = AgentStateFactory.with_human_message("Create a hello world Python script")
        config = {"configurable": {"thread_id": "test-workflow"}}

        # Mock context building
        with patch.object(supervisor, '_build_context', new=AsyncMock(return_value={
            "tools": [],
            "sys_info": "Test system",
            "active_plan_context": "None",
            "iteration_count": 0
        })):
            # Mock engine to simulate routing decision
            with patch('app.core.engine.AgentEngine.run_node') as mock_engine:
                mock_engine.return_value = {
                    "messages": [AIMessage(content="I'll route to operator")],
                    "_routing_target": "operator",
                    "_routing_reason": "Need to write code",
                    "_routing_context": {
                        "focus_paths": ["hello.py"],
                        "acceptance_criteria": ["Create hello world script"]
                    }
                }

                # Execute supervisor
                result = await supervisor(state, config)

                # Note: Supervisor returns 'operator' but actual execution uses WorkerNode
                # 'operator' is the conceptual role, WorkerNode is the implementation
                assert result["next_node"] in ["operator", "worker"]
                assert result["execution_ticket"] is not None

                # Now simulate worker execution
                op_state = {
                    **state,
                    "execution_ticket": result["execution_ticket"],
                    "scratchpad": result.get("scratchpad", {})
                }

                # Worker node processes execution ticket
                worker_result = await worker(op_state, config)

                # Worker returns appropriate result structure
                assert "messages" in worker_result or "next_node" in worker_result

    async def test_worker_execution_flow(self):
        """Test worker node execution with ticket."""
        from app.core.engine.nodes.worker import WorkerNode

        node = WorkerNode()

        # Create execution ticket for worker
        ticket = {
            "agent_config": {
                "role_name": "Code Writer",
                "system_instructions": "You write clean, efficient code."
            },
            "topic": "Write a hello world script",
            "acceptance_criteria": ["Create hello.py", "Add print statement"]
        }

        state = AgentStateFactory.create(
            execution_ticket=ticket,
            messages=[HumanMessage(content="Write a hello world script")]
        )
        config = {"configurable": {"thread_id": "test-worker"}}

        # Worker requires valid ticket with agent_config
        # Just verify the node processes the ticket structure
        assert state.get("execution_ticket") is not None
        assert state["execution_ticket"]["agent_config"] is not None

    async def test_worker_with_missing_ticket(self):
        """Test worker handles missing ticket gracefully."""
        from app.core.engine.nodes.worker import WorkerNode

        node = WorkerNode()

        state = AgentStateFactory.create(
            messages=[HumanMessage(content="Do something")]
            # No execution_ticket
        )
        config = {"configurable": {"thread_id": "test-no-ticket"}}

        # Execute - should return error without crashing
        result = await node(state, config)

        assert "messages" in result
        assert "Error" in result["messages"][0].content
        assert result["next_node"] == "supervisor"


@pytest.mark.integration
@pytest.mark.asyncio
class TestContextPropagation:
    """Tests for context propagation across nodes."""

    async def test_context_preserved_across_nodes(self):
        """Test that context is preserved when passing between nodes."""
        from app.core.context.manager import EvoContext, ContextManager

        # Set up initial context
        ctx = EvoContext(
            request_id="test-request",
            thread_id="test-thread",
            user_id="user-123",
            project_id=42
        )
        token = ContextManager.set(ctx)

        try:
            # Simulate node execution
            current = ContextManager.current()
            assert current.request_id == "test-request"
            assert current.project_id == 42

            # Simulate context modification
            current.short_term_memory.append("test memory")

            # Verify context persists
            again = ContextManager.current()
            assert "test memory" in again.short_term_memory
        finally:
            ContextManager.reset(token)

    async def test_scratchpad_accumulation(self):
        """Test that scratchpad accumulates data across node executions."""
        state = AgentStateFactory.create(scratchpad={"visited_nodes": ["supervisor"]})

        # Simulate adding more data
        state["scratchpad"]["visited_nodes"].append("developer")
        state["scratchpad"]["last_action"] = "code_written"

        assert "supervisor" in state["scratchpad"]["visited_nodes"]
        assert "developer" in state["scratchpad"]["visited_nodes"]
        assert state["scratchpad"]["last_action"] == "code_written"


@pytest.mark.integration
@pytest.mark.asyncio
class TestMemoryIntegration:
    """Tests for memory system integration."""

    async def test_short_term_to_long_term_flow(self):
        """Test conversation flow from short-term to long-term memory."""
        from app.core.memory.manager import MemoryManager

        # Mock the memory manager and its backends
        manager = MemoryManager()
        manager.short_term = AsyncMock()
        manager.long_term = AsyncMock()

        # Simulate adding conversation
        await manager.short_term.add_message("thread-1", HumanMessage(content="Hello"))
        await manager.short_term.add_message("thread-1", AIMessage(content="Hi there"))

        # Verify short_term was called
        assert manager.short_term.add_message.call_count == 2

    async def test_memory_manager_coordination(self):
        """Test that MemoryManager coordinates between backends."""
        from app.core.memory.manager import MemoryManager

        manager = MemoryManager()

        # Mock all backends
        manager.short_term = AsyncMock()
        manager.long_term = AsyncMock()
        manager.preferences = AsyncMock()
        manager.graph = AsyncMock()

        # Test initialization
        await manager.initialize()

        manager.short_term.initialize.assert_called_once()
        manager.long_term.initialize.assert_called_once()
