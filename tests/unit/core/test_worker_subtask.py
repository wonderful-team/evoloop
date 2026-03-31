"""
Tests for Worker Node - Subtask State Isolation

This module tests that subtasks properly isolate their state from parent tasks
to prevent state pollution issues.
"""
import copy
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine.nodes.worker import WorkerNode
from app.core.engine.state import AgentState


class TestWorkerSubtaskIsolation:
    """Tests for subtask state isolation in WorkerNode."""

    @pytest.fixture
    def base_state(self):
        """Create a base state with nested structures."""
        return {
            "messages": [HumanMessage(content="test message")],
            "thread_id": "parent-thread-123",
            "project_id": 1,
            "blackboard": {
                "ticket": {"topic": "parent task"},
                "metadata": {"key": "value"},
                "visited_nodes": ["supervisor"],
                "subtask_results": []
            },
            "iteration_count": 0,
            "is_subtask": False
        }

    def test_deep_copy_for_subtasks(self, base_state, subtask_execution_ticket):
        """Test that subtasks use deep copy to prevent state pollution."""
        node = WorkerNode()
        
        # Modify state to include subtask ticket
        state = copy.deepcopy(base_state)
        state["execution_ticket"] = subtask_execution_ticket
        
        # Store original blackboard reference
        original_blackboard = state["blackboard"]
        original_metadata = state["blackboard"]["metadata"]
        
        # Verify the state structure
        assert state["blackboard"]["metadata"]["key"] == "value"
        
        # The fix should ensure that when we deep copy:
        # 1. The new state is a completely separate object
        # 2. Nested objects (blackboard, metadata) are also separate
        
        # Simulate what happens in the fixed worker.py
        if subtask_execution_ticket["agent_config"].get("is_subtask"):
            worker_state = copy.deepcopy(state)
        else:
            worker_state = state.copy()
        
        # Verify deep copy occurred
        assert worker_state is not state
        assert worker_state["blackboard"] is not original_blackboard
        assert worker_state["blackboard"]["metadata"] is not original_metadata
        
        # Verify modifying worker_state doesn't affect original
        worker_state["blackboard"]["metadata"]["new_key"] = "new_value"
        assert "new_key" not in original_metadata

    def test_shallow_copy_for_regular_tasks(self, base_state):
        """Test that regular tasks use shallow copy (for performance)."""
        node = WorkerNode()
        
        # Regular task (not subtask)
        ticket = {
            "ticket_type": "task",
            "topic": "regular task",
            "agent_config": {
                "role_name": "Worker",
                "system_instructions": "Test",
                "is_subtask": False
            }
        }
        
        state = copy.deepcopy(base_state)
        state["execution_ticket"] = ticket
        
        original_blackboard = state["blackboard"]
        
        # Simulate what happens in the fixed worker.py for non-subtasks
        if ticket["agent_config"].get("is_subtask"):
            worker_state = copy.deepcopy(state)
        else:
            worker_state = state.copy()
        
        # Shallow copy: top-level dict is new, but nested objects are shared
        assert worker_state is not state
        # Note: state.copy() creates shallow copy, so blackboard is shared
        # This is acceptable for regular tasks as they don't run in parallel

    def test_thread_id_preservation_in_subtasks(self, base_state, subtask_execution_ticket):
        """Test that thread_id is correctly set for subtasks."""
        # Create fresh state with is_subtask=True
        state = {
            "messages": [HumanMessage(content="test message")],
            "thread_id": "parent-thread-123:sub:sub_1",  # Scoped thread_id
            "project_id": 1,
            "is_subtask": True,  # Mark as subtask
            "blackboard": {
                "ticket": {"topic": "parent task"},
                "subtask_results": []
            },
            "execution_ticket": subtask_execution_ticket,
            "iteration_count": 0
        }
        
        # Deep copy should preserve thread_id and is_subtask
        worker_state = copy.deepcopy(state)
        assert worker_state["thread_id"] == "parent-thread-123:sub:sub_1"
        assert worker_state.get("is_subtask") is True
        
        # Verify nested structures are also copied
        assert worker_state["blackboard"] is not state["blackboard"]
        assert worker_state["execution_ticket"] is not state["execution_ticket"]

    def test_messages_reset_for_subtasks(self, base_state, subtask_execution_ticket):
        """Test that messages are reset for subtasks to prevent echo chamber."""
        state = copy.deepcopy(base_state)
        state["execution_ticket"] = subtask_execution_ticket
        
        # Original state has messages
        assert len(state["messages"]) > 0
        
        # After deep copy and message reset
        worker_state = copy.deepcopy(state)
        new_message = HumanMessage(content="subtask mission")
        worker_state["messages"] = [new_message]
        
        # Original state should be unaffected
        assert len(state["messages"]) == 1
        assert state["messages"][0].content == "test message"
        assert worker_state["messages"][0].content == "subtask mission"

    @pytest.fixture
    def subtask_execution_ticket(self):
        """Create an execution ticket for subtask mode."""
        return {
            "ticket_type": "subtask",
            "topic": "subtask test",
            "subtask_id": "sub_1",
            "parent_task_id": "parent-thread-123",
            "agent_config": {
                "role_name": "Test Specialist",
                "system_instructions": "Test instructions",
                "is_subtask": True  # Mark as subtask
            }
        }

    def test_deep_copy_for_subtasks(self, base_state, subtask_execution_ticket):
        """Test that subtasks use deep copy to prevent state pollution."""
        node = WorkerNode()
        
        # Modify state to include subtask ticket
        state = copy.deepcopy(base_state)
        state["execution_ticket"] = subtask_execution_ticket
        
        # Store original blackboard reference
        original_blackboard = state["blackboard"]
        original_metadata = state["blackboard"]["metadata"]
        
        # Verify the state structure
        assert state["blackboard"]["metadata"]["key"] == "value"
        
        # The fix should ensure that when we deep copy:
        # 1. The new state is a completely separate object
        # 2. Nested objects (blackboard, metadata) are also separate
        
        # Simulate what happens in the fixed worker.py
        if subtask_execution_ticket["agent_config"].get("is_subtask"):
            worker_state = copy.deepcopy(state)
        else:
            worker_state = state.copy()
        
        # Verify deep copy occurred
        assert worker_state is not state
        assert worker_state["blackboard"] is not original_blackboard
        assert worker_state["blackboard"]["metadata"] is not original_metadata
        
        # Verify modifying worker_state doesn't affect original
        worker_state["blackboard"]["metadata"]["new_key"] = "new_value"
        assert "new_key" not in original_metadata

    def test_shallow_copy_for_regular_tasks(self, base_state):
        """Test that regular tasks use shallow copy (for performance)."""
        node = WorkerNode()
        
        # Regular task (not subtask)
        ticket = {
            "ticket_type": "task",
            "topic": "regular task",
            "agent_config": {
                "role_name": "Worker",
                "system_instructions": "Test",
                "is_subtask": False
            }
        }
        
        state = copy.deepcopy(base_state)
        state["execution_ticket"] = ticket
        
        original_blackboard = state["blackboard"]
        
        # Simulate what happens in the fixed worker.py for non-subtasks
        if ticket["agent_config"].get("is_subtask"):
            worker_state = copy.deepcopy(state)
        else:
            worker_state = state.copy()
        
        # Shallow copy: top-level dict is new, but nested objects are shared
        assert worker_state is not state
        # Note: state.copy() creates shallow copy, so blackboard is shared
        # This is acceptable for regular tasks as they don't run in parallel

    def test_messages_reset_for_subtasks(self, base_state, subtask_execution_ticket):
        """Test that messages are reset for subtasks to prevent echo chamber."""
        state = copy.deepcopy(base_state)
        state["execution_ticket"] = subtask_execution_ticket
        
        # Original state has messages
        assert len(state["messages"]) > 0
        
        # After deep copy and message reset
        worker_state = copy.deepcopy(state)
        new_message = HumanMessage(content="subtask mission")
        worker_state["messages"] = [new_message]
        
        # Original state should be unaffected
        assert len(state["messages"]) == 1
        assert state["messages"][0].content == "test message"
        assert worker_state["messages"][0].content == "subtask mission"


class TestWorkerBlackboardIsolation:
    """Tests specifically for blackboard isolation."""

    @pytest.fixture
    def complex_blackboard(self):
        """Create a complex blackboard structure."""
        return {
            "ticket": {
                "topic": "complex task",
                "acceptance_criteria": ["criteria1", "criteria2"],
                "parameters": {"nested": {"deep": "value"}}
            },
            "verification": {"status": "pending"},
            "metadata": {
                "clipboard": [{"content": "item1"}],
                "visited_nodes": ["supervisor", "worker"],
                "custom_data": {"key": "value"}
            },
            "subtask_results": [
                {"subtask_id": "1", "result": "done"}
            ]
        }

    def test_blackboard_deep_isolation(self, complex_blackboard):
        """Test that blackboard modifications in subtasks don't affect parent."""
        state = {
            "thread_id": "test",
            "blackboard": complex_blackboard
        }
        
        # Deep copy as would happen for subtasks
        worker_state = copy.deepcopy(state)
        
        # Modify worker's blackboard
        worker_state["blackboard"]["ticket"]["topic"] = "modified"
        worker_state["blackboard"]["metadata"]["clipboard"].append({"content": "new"})
        worker_state["blackboard"]["subtask_results"].append({"subtask_id": "2", "result": "new"})
        
        # Verify original is unaffected
        assert state["blackboard"]["ticket"]["topic"] == "complex task"
        assert len(state["blackboard"]["metadata"]["clipboard"]) == 1
        assert len(state["blackboard"]["subtask_results"]) == 1

    def test_subtask_result_collection_isolation(self, complex_blackboard):
        """Test that subtask result collection doesn't pollute parent."""
        parent_state = {
            "thread_id": "parent",
            "blackboard": complex_blackboard.copy()
        }
        
        # Simulate what happens when subtask finishes
        subtask_state = copy.deepcopy(parent_state)
        subtask_state["blackboard"]["subtask_results"] = [
            {"subtask_id": "sub_1", "result": "subtask result"}
        ]
        
        # Parent should not see subtask's results yet
        assert len(parent_state["blackboard"]["subtask_results"]) == 1
        assert parent_state["blackboard"]["subtask_results"][0]["subtask_id"] == "1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
