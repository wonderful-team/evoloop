"""
Tests for Graph Node Flow — Long-Horizon Routing Paths

Verifies the conditional routing logic that enables long-horizon tasks:
1. route_finish respects INCOMPLETE audit outcome
2. route_supervisor respects dynamic max_supervisor_steps from blackboard
3. Supervisor -> Worker loopback when plan is incomplete
"""

import pytest
from unittest.mock import MagicMock

from app.core.engine.routers import route_finish, route_supervisor, RoutingTarget
from app.core.engine.state import AgentState
from langgraph.types import Send


class TestRouteFinishIncomplete:
    """Tests for route_finish with INCOMPLETE audit outcome."""

    def test_incomplete_outcome_routes_to_supervisor(self):
        """INCOMPLETE final_outcome must loop back to Supervisor."""
        state = AgentState(messages=[], final_outcome="INCOMPLETE")
        result = route_finish(state)
        assert result == RoutingTarget.SUPERVISOR

    def test_complete_outcome_routes_to_end(self):
        """COMPLETE final_outcome should go to END."""
        state = AgentState(messages=[], final_outcome="COMPLETE")
        result = route_finish(state)
        assert result == RoutingTarget.END

    def test_no_outcome_routes_to_end(self):
        """No final_outcome should default to END."""
        state = AgentState(messages=[])
        result = route_finish(state)
        assert result == RoutingTarget.END

    def test_blocked_by_hook_takes_precedence(self):
        """blocked_by_hook should still route to SUPERVISOR."""
        state = AgentState(
            messages=[],
            blocked_by_hook=True,
            final_outcome="COMPLETE",  # Even if complete, hook blocks
        )
        result = route_finish(state)
        assert result == RoutingTarget.SUPERVISOR

    def test_explicit_end_overrides_all(self):
        """state.next_node == END should override everything."""
        state = AgentState(
            messages=[],
            blocked_by_hook=True,
            final_outcome="INCOMPLETE",
            next_node=RoutingTarget.END,
        )
        result = route_finish(state)
        assert result == RoutingTarget.END

    def test_case_insensitive_incomplete(self):
        """INCOMPLETE matching should be case-insensitive."""
        for variant in ["incomplete", "Incomplete", "INCOMPLETE"]:
            state = AgentState(messages=[], final_outcome=variant)
            result = route_finish(state)
            assert result == RoutingTarget.SUPERVISOR, f"Failed for variant: {variant}"


class TestRouteSupervisorDynamicLimits:
    """Tests for route_supervisor with dynamic max_supervisor_steps."""

    def test_default_limit_without_blackboard_override(self):
        """Without blackboard override, use settings.SUPERVISOR_AGENT_MAX_STEPS."""
        from app.core.config import settings
        state = AgentState(
            messages=[],
            iteration_count=settings.SUPERVISOR_AGENT_MAX_STEPS,
        )
        result = route_supervisor(state)
        assert result == RoutingTarget.FINISH

    def test_dynamic_limit_from_blackboard(self):
        """Blackboard metadata max_supervisor_steps overrides default."""
        from app.core.config import settings
        custom_limit = settings.SUPERVISOR_AGENT_MAX_STEPS + 20
        state = AgentState(
            messages=[],
            max_supervisor_steps=custom_limit,
            iteration_count=settings.SUPERVISOR_AGENT_MAX_STEPS + 10,  # Below custom limit
            next_node="supervisor",  # Set next_node to avoid default "finish" fallback
        )
        result = route_supervisor(state)
        # It won't be FINISH because iteration_count < custom_limit
        assert result != RoutingTarget.FINISH

    def test_dynamic_limit_termination(self):
        """Blackboard dynamic limit should trigger termination when exceeded."""
        state = AgentState(
            messages=[],
            max_supervisor_steps=50,
            iteration_count=50,  # At limit
        )
        result = route_supervisor(state)
        assert result == RoutingTarget.FINISH

    def test_long_horizon_higher_than_default(self):
        """Long-horizon limit must be higher than default."""
        from app.core.config import settings
        assert settings.LONG_HORIZON_SUPERVISOR_MAX_STEPS > settings.SUPERVISOR_AGENT_MAX_STEPS

    def test_blackboard_none_uses_default(self):
        """Missing blackboard should fall back to default settings."""
        from app.core.config import settings
        state = AgentState(
            messages=[],
            iteration_count=settings.SUPERVISOR_AGENT_MAX_STEPS,
        )
        result = route_supervisor(state)
        assert result == RoutingTarget.FINISH
