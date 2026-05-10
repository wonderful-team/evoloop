"""
Tests for Supervisor Plan Completeness Gate

Verifies that the Supervisor does NOT route to FINISH when the plan
still has pending steps, forcing continued WORKER execution.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from app.core.engine.nodes.supervisor import SupervisorNode, _plan_has_pending_steps
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.blackboard import BlackboardState, BlackboardMetadata, PlanProgress
from langchain_core.runnables import RunnableConfig


class TestPlanHasPendingSteps:
    """Unit tests for the _plan_has_pending_steps helper."""

    def test_none_plan_returns_false(self):
        assert _plan_has_pending_steps(None) is False

    def test_empty_plan_returns_false(self):
        assert _plan_has_pending_steps({}) is False
        assert _plan_has_pending_steps("{}") is False

    def test_all_done_steps_returns_false(self):
        plan = {
            "steps": [
                {"status": "done"},
                {"status": "completed"},
                {"status": "success"},
                {"status": "finished"},
            ]
        }
        assert _plan_has_pending_steps(plan) is False

    def test_pending_steps_returns_true(self):
        plan = {
            "steps": [
                {"status": "done"},
                {"status": "pending"},
            ]
        }
        assert _plan_has_pending_steps(plan) is True

    def test_in_progress_steps_returns_true(self):
        plan = {
            "steps": [
                {"status": "in_progress"},
                {"status": "done"},
            ]
        }
        assert _plan_has_pending_steps(plan) is True

    def test_nested_plan_schema(self):
        plan = {"plan": {"steps": [{"status": "todo"}, {"status": "done"}]}}
        assert _plan_has_pending_steps(plan) is True

    def test_json_string_plan(self):
        plan_json = '{"steps": [{"status": "pending"}, {"status": "done"}]}'
        assert _plan_has_pending_steps(plan_json) is True

    def test_mixed_case_status(self):
        plan = {
            "steps": [
                {"status": "DONE"},
                {"status": "Pending"},
            ]
        }
        assert _plan_has_pending_steps(plan) is True


class TestSupervisorPlanCompletenessGate:
    """Integration tests for SupervisorNode.prepare_state plan gate."""

    @pytest.fixture
    def supervisor(self):
        return SupervisorNode()

    @pytest.fixture
    def config(self):
        return RunnableConfig(configurable={"thread_id": "test-thread"})

    def _make_state(self, worker_outcome=None, plan_progress=None, structured_plan=None) -> AgentState:
        """Helper to construct a state with proper blackboard."""
        metadata = BlackboardMetadata()
        if plan_progress:
            metadata.plan_progress = plan_progress
        blackboard = BlackboardState(metadata=metadata)
        if worker_outcome:
            blackboard.worker_outcome = worker_outcome
        return AgentState(
            messages=[],
            blackboard=blackboard,
            iteration_count=0,
            structured_plan=structured_plan,
        )

    @pytest.mark.asyncio
    async def test_no_plan_routes_to_finish(self, supervisor, config):
        """When there's no plan, worker success should route to FINISH normally."""
        state = self._make_state(worker_outcome="success")

        with patch.object(supervisor, "_emit_status", new_callable=AsyncMock):
            result = await supervisor.prepare_state(state, config)

        assert result is not None
        assert result.next_node == RoutingTarget.FINISH

    @pytest.mark.asyncio
    async def test_plan_complete_routes_to_finish(self, supervisor, config):
        """When plan is fully complete, worker success should route to FINISH."""
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

        with patch.object(supervisor, "_emit_status", new_callable=AsyncMock):
            result = await supervisor.prepare_state(state, config)

        assert result is not None
        assert result.next_node == RoutingTarget.FINISH

    @pytest.mark.asyncio
    async def test_plan_incomplete_routes_to_worker(self, supervisor, config):
        """When plan has pending steps, worker success should route to WORKER."""
        state = self._make_state(
            worker_outcome="success",
            plan_progress=PlanProgress(total_steps=5, completed_steps=2),
        )

        with patch.object(supervisor, "_emit_status", new_callable=AsyncMock):
            result = await supervisor.prepare_state(state, config)

        assert result is not None
        assert result.next_node == RoutingTarget.WORKER
        assert result.iteration_count == 1

    @pytest.mark.asyncio
    async def test_structured_plan_pending_routes_to_worker(self, supervisor, config):
        """Fallback: structured_plan with pending steps routes to WORKER."""
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

        with patch.object(supervisor, "_emit_status", new_callable=AsyncMock):
            result = await supervisor.prepare_state(state, config)

        assert result is not None
        assert result.next_node == RoutingTarget.WORKER

    @pytest.mark.asyncio
    async def test_worker_failure_clears_ticket(self, supervisor, config):
        """Worker failure should clear ticket for re-planning."""
        state = self._make_state(worker_outcome="failed")
        # Set a ticket to verify it's cleared
        state.blackboard.ticket = MagicMock()

        with patch.object(supervisor, "_emit_status", new_callable=AsyncMock):
            result = await supervisor.prepare_state(state, config)

        # When worker fails, prepare_state returns None (fallback takes over)
        assert result is None
        assert state.blackboard.ticket is None

    @pytest.mark.asyncio
    async def test_no_worker_outcome_returns_none(self, supervisor, config):
        """When there's no worker outcome, prepare_state returns None."""
        state = self._make_state()

        with patch.object(supervisor, "_emit_status", new_callable=AsyncMock):
            result = await supervisor.prepare_state(state, config)

        assert result is None
