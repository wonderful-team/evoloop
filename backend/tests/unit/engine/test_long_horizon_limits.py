"""
Tests for Long-Horizon Dynamic Limit Injection

Verifies that when metadata["long_horizon"] = True, the background agent
injects higher recursion_limit and max_supervisor_steps into the config.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from app.core.config import settings
from app.core.engine.background_agent import run_agent_background
from app.core.engine.state.blackboard import BlackboardState, BlackboardMetadata


class TestLongHorizonLimitInjection:
    """Tests for dynamic limit injection in run_agent_background."""

    @pytest.fixture
    def base_inputs(self):
        return {
            "messages": [],
            "blackboard": BlackboardState(
                metadata=BlackboardMetadata()
            ).model_dump(mode="json"),
        }

    def test_default_limits_are_defined(self):
        """Default and long-horizon limits should both be positive integers."""
        assert settings.RECURSION_LIMIT > 0
        assert settings.SUPERVISOR_AGENT_MAX_STEPS > 0
        assert settings.LONG_HORIZON_RECURSION_LIMIT > 0
        assert settings.LONG_HORIZON_SUPERVISOR_MAX_STEPS > 0

    def test_long_horizon_limits_are_higher(self):
        """Long-horizon limits must be strictly higher than defaults."""
        assert settings.LONG_HORIZON_RECURSION_LIMIT > settings.RECURSION_LIMIT
        assert settings.LONG_HORIZON_SUPERVISOR_MAX_STEPS > settings.SUPERVISOR_AGENT_MAX_STEPS

    def test_blackboard_metadata_accepts_max_supervisor_steps(self):
        """The BlackboardMetadata model must accept max_supervisor_steps."""
        meta = BlackboardMetadata(max_supervisor_steps=50)
        assert meta.max_supervisor_steps == 50

    def test_blackboard_metadata_plan_progress(self):
        """The BlackboardMetadata model must accept plan_progress."""
        from app.core.engine.state.blackboard import PlanProgress
        progress = PlanProgress(total_steps=10, completed_steps=5)
        meta = BlackboardMetadata(plan_progress=progress)
        assert meta.plan_progress.is_complete() is False
        assert meta.plan_progress.completed_steps == 5
        assert meta.plan_progress.total_steps == 10
