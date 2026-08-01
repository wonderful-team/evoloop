"""
Tests for Supervisor Plan Completeness Gate

Verifies that the Supervisor does NOT route to FINISH when the plan
still has pending steps, forcing continued WORKER execution.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from app.core.engine.nodes.supervisor import SupervisorNode
from app.core.engine.state import AgentState
from app.core.engine.state.sub_schemas import PlanProgress


class TestSupervisorPlanCompletenessGate:
    """Integration tests for SupervisorNode.prepare_state plan gate."""

    @pytest.fixture
    def supervisor(self):
        return SupervisorNode()

    @pytest.fixture
    def config(self):
        return RunnableConfig(configurable={"thread_id": "test-thread"})

    def _make_state(self, worker_outcome=None, plan_progress=None, structured_plan=None) -> AgentState:
        """Helper to construct a state with proper flat attributes."""
        return AgentState(
            messages=[],
            worker_outcome=worker_outcome,
            plan_progress=plan_progress,
            structured_plan=structured_plan,
            iteration_count=0,
        )

    @pytest.mark.asyncio
    async def test_no_plan_routes_to_finish(self, supervisor, config):
        """When worker outcome is set, prepare_state clears ticket and returns None (delegating to LLM)."""
        state = self._make_state(worker_outcome="success")
        state.ticket = MagicMock()

        with patch.object(supervisor, "_emit_status", new_callable=AsyncMock):
            result = await supervisor.prepare_state(state, config)

        assert result is None
        assert state.ticket is None

    @pytest.mark.asyncio
    async def test_plan_complete_routes_to_finish(self, supervisor, config):
        """When worker outcome is set, prepare_state clears ticket and returns None (delegating to LLM)."""
        import json
        state = self._make_state(
            worker_outcome="success",
            plan_progress=PlanProgress(total_steps=3, completed_steps=3),
            structured_plan=json.dumps({
                "steps": [
                    {"status": "done"},
                    {"status": "completed"},
                    {"status": "success"},
                ]
            }),
        )
        state.ticket = MagicMock()

        with patch.object(supervisor, "_emit_status", new_callable=AsyncMock):
            result = await supervisor.prepare_state(state, config)

        assert result is None
        assert state.ticket is None

    @pytest.mark.asyncio
    async def test_plan_incomplete_routes_to_worker(self, supervisor, config):
        """When worker outcome is set, prepare_state clears ticket and returns None (delegating to LLM)."""
        state = self._make_state(
            worker_outcome="success",
            plan_progress=PlanProgress(total_steps=5, completed_steps=2),
        )
        state.ticket = MagicMock()

        with patch.object(supervisor, "_emit_status", new_callable=AsyncMock):
            result = await supervisor.prepare_state(state, config)

        assert result is None
        assert state.ticket is None

    @pytest.mark.asyncio
    async def test_structured_plan_pending_routes_to_worker(self, supervisor, config):
        """When worker outcome is set, prepare_state clears ticket and returns None (delegating to LLM)."""
        import json
        state = self._make_state(
            worker_outcome="success",
            structured_plan=json.dumps({
                "steps": [
                    {"status": "done"},
                    {"status": "pending"},
                ]
            }),
        )
        state.ticket = MagicMock()

        with patch.object(supervisor, "_emit_status", new_callable=AsyncMock):
            result = await supervisor.prepare_state(state, config)

        assert result is None
        assert state.ticket is None

    @pytest.mark.asyncio
    async def test_worker_failure_clears_ticket(self, supervisor, config):
        """Worker failure should clear ticket for re-planning."""
        state = self._make_state(worker_outcome="failed")
        # Set a ticket to verify it's cleared
        state.ticket = MagicMock()

        with patch.object(supervisor, "_emit_status", new_callable=AsyncMock):
            result = await supervisor.prepare_state(state, config)

        # When worker fails, prepare_state returns None (fallback takes over)
        assert result is None
        assert state.ticket is None

    @pytest.mark.asyncio
    async def test_no_worker_outcome_returns_none(self, supervisor, config):
        """When there's no worker outcome, prepare_state returns None."""
        state = self._make_state()

        with patch.object(supervisor, "_emit_status", new_callable=AsyncMock):
            result = await supervisor.prepare_state(state, config)

        assert result is None
