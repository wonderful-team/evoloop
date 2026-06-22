"""
Tests for WorkerNode.prepare_state loading plan from DB.

Verifies that Worker loads the existing plan from the database when
state.structured_plan is empty (e.g. after route_to from Supervisor).
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from langchain_core.runnables import RunnableConfig

from app.core.engine.nodes.worker import WorkerNode
from app.core.engine.state import AgentState
from app.core.engine.state.config import ExecutionTicket, AgentRuntimeConfig


class TestWorkerPlanLoad:
    """Tests for Worker plan loading from DB."""

    @pytest.fixture
    def worker_node(self):
        return WorkerNode()

    @pytest.fixture
    def config(self):
        return RunnableConfig(configurable={"thread_id": "test-thread", "model": "test-model"})

    def _make_state(self, structured_plan=None, current_plan=None):
        """Helper to create AgentState with ticket."""
        ticket = ExecutionTicket(
            ticket_type="task",
            topic="test",
            agent_config=AgentRuntimeConfig(role_name="Worker"),
        )
        state = AgentState(
            thread_id="test-thread",
            messages=[],
            ticket=ticket,
            current_plan=current_plan,
        )
        if structured_plan is not None:
            state.structured_plan = structured_plan
        return state

    @pytest.mark.asyncio
    async def test_load_plan_from_db_when_empty(self, worker_node, config):
        """When structured_plan and current_plan are empty, load from DB."""
        state = self._make_state(structured_plan=None, current_plan=None)

        plan_dict = {
            "id": "plan-123",
            "title": "Wiki Plan",
            "status": "active",
            "steps": [
                {"id": "s1", "title": "Step 1", "status": "completed", "order": 0},
                {"id": "s2", "title": "Step 2", "status": "pending", "order": 1},
            ],
        }

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = plan_dict
            result = await worker_node.prepare_state(state, config)

        assert result is None  # prepare_state returns None on success
        assert state.structured_plan is not None
        assert state.structured_plan["id"] == "plan-123"
        assert state.structured_plan["title"] == "Wiki Plan"
        assert len(state.structured_plan["steps"]) == 2
        assert state.structured_plan["steps"][0]["id"] == "s1"
        assert state.structured_plan["steps"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_skip_load_when_structured_plan_exists(self, worker_node, config):
        """When structured_plan already exists, skip DB load."""
        existing_plan = {"id": "existing", "title": "Existing Plan", "steps": []}
        state = self._make_state(structured_plan=existing_plan)

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            result = await worker_node.prepare_state(state, config)
            mock_to_thread.assert_not_called()

        assert state.structured_plan == existing_plan

    @pytest.mark.asyncio
    async def test_skip_load_when_current_plan_exists(self, worker_node, config):
        """When current_plan exists, skip DB load."""
        state = self._make_state(current_plan="some plan text")

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            result = await worker_node.prepare_state(state, config)
            mock_to_thread.assert_not_called()

        assert state.structured_plan is None
        assert state.current_plan == "some plan text"

    @pytest.mark.asyncio
    async def test_skip_load_when_no_thread_id(self, worker_node, config):
        """When thread_id is missing in config, skip gracefully."""
        state = self._make_state()
        config_no_thread = RunnableConfig(configurable={"model": "test-model"})

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            result = await worker_node.prepare_state(state, config_no_thread)
            mock_to_thread.assert_not_called()

        assert state.structured_plan is None
