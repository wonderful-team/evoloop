import pytest

from app.core.engine.state import AgentState
from app.core.engine.state.sub_schemas import PlanProgress


class TestPlanProgress:
    """Unit tests for PlanProgress tracking model."""

    def test_is_complete_when_equal(self):
        progress = PlanProgress(total_steps=5, completed_steps=5)
        assert progress.is_complete() is True

    def test_is_complete_when_greater(self):
        progress = PlanProgress(total_steps=5, completed_steps=6)
        assert progress.is_complete() is True

    def test_is_not_complete_when_less(self):
        progress = PlanProgress(total_steps=5, completed_steps=3)
        assert progress.is_complete() is False

    def test_zero_steps_is_complete(self):
        progress = PlanProgress(total_steps=0, completed_steps=0)
        assert progress.is_complete() is True

    def test_plan_id_field(self):
        progress = PlanProgress(total_steps=3, completed_steps=1, plan_id="plan-123")
        assert progress.plan_id == "plan-123"


class TestAgentStateSerialization:
    """Tests for flat AgentState serialization round-trip."""

    def test_plan_progress_round_trip(self):
        original = AgentState(
            plan_progress=PlanProgress(total_steps=15, completed_steps=10, plan_id="abc")
        )
        data = original.model_dump(mode="json")
        restored = AgentState.model_validate(data)
        assert restored.plan_progress.total_steps == 15
        assert restored.plan_progress.completed_steps == 10
        assert restored.plan_progress.plan_id == "abc"

    def test_max_supervisor_steps_round_trip(self):
        original = AgentState(max_supervisor_steps=75)
        data = original.model_dump(mode="json")
        restored = AgentState.model_validate(data)
        assert restored.max_supervisor_steps == 75
