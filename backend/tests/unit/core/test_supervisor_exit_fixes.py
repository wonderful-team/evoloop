
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage
from app.core.engine.nodes.supervisor import SupervisorNode
from app.core.engine.nodes.finish import finish_node
from app.core.engine.state import AgentState

@pytest.mark.asyncio
async def test_supervisor_node_concept_search_failure_fix():
    """Verify that SupervisorNode doesn't crash when found is not defined due to search failure."""
    node = SupervisorNode()
    state = {
        "messages": [HumanMessage(content="Hello")],
        "project_id": 1,
        "iteration_count": 0
    }
    config = {"configurable": {"thread_id": "test", "working_directory": "/tmp"}}
    
    # Mock memory_manager to simulate a state where found might not be initialized in old code
    # Actually, we just need to ensure the code path runs without error
    with patch("app.core.memory.memory_manager.long_term.search_concepts", side_effect=Exception("Search failed")):
        with patch("app.core.engine.AgentEngine.run_node", new=AsyncMock(return_value={"messages": [AIMessage(content="OK")]})):
            # This should not raise UnboundLocalError
            result = await node(state, config)
            assert result["next_node"] == "finish"

@pytest.mark.asyncio
async def test_finish_node_global_mode_fix():
    """Verify that FinishNode proceeds in Global Mode (no cwd)."""
    state = {
        "messages": [AIMessage(content="Final summary")],
        "current_plan": "Done",
        "project_id": 0
    }
    # No working_directory in config
    config = {"configurable": {"thread_id": "test"}}
    
    with patch("app.core.engine.AgentEngine.run_node", new=AsyncMock(return_value={"messages": [AIMessage(content="Verified")]})):
        with patch("app.core.engine.nodes.finish._trigger_session_recording") as mock_record:
            # This should not return error early
            result = await finish_node(state, config)
            assert result["next_node"] == "END"
            mock_record.assert_called_once()
