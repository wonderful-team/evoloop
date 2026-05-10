"""
Tests for Blackboard State Models

Verifies PlanProgress, BlackboardMetadata, and merge behavior
for long-horizon tracking fields.
"""

import pytest

from app.core.engine.state.blackboard import (
    BlackboardState,
    BlackboardMetadata,
    PlanProgress,
    merge_blackboard,
)


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


class TestBlackboardMetadata:
    """Tests for BlackboardMetadata new fields."""

    def test_max_supervisor_steps_field(self):
        meta = BlackboardMetadata(max_supervisor_steps=50)
        assert meta.max_supervisor_steps == 50

    def test_plan_progress_field(self):
        progress = PlanProgress(total_steps=10, completed_steps=5)
        meta = BlackboardMetadata(plan_progress=progress)
        assert meta.plan_progress == progress
        assert meta.plan_progress.is_complete() is False

    def test_default_values(self):
        meta = BlackboardMetadata()
        assert meta.max_supervisor_steps is None
        assert meta.plan_progress is None
        assert meta.final_outcome is None
        assert meta.blocked_by_hook is None

    def test_all_fields_together(self):
        meta = BlackboardMetadata(
            tool_memory={"key": "value"},
            final_outcome="COMPLETE",
            max_supervisor_steps=50,
            plan_progress=PlanProgress(total_steps=20, completed_steps=20),
            blocked_by_hook=False,
        )
        assert meta.final_outcome == "COMPLETE"
        assert meta.max_supervisor_steps == 50
        assert meta.plan_progress.is_complete() is True


class TestBlackboardMerge:
    """Tests for blackboard merge behavior with new fields."""

    def test_merge_preserves_plan_progress(self):
        old = BlackboardState(
            metadata=BlackboardMetadata(
                plan_progress=PlanProgress(total_steps=10, completed_steps=5)
            )
        )
        new = BlackboardState(
            metadata=BlackboardMetadata(
                final_outcome="INCOMPLETE"
            )
        )
        merged = merge_blackboard(old, new)
        # MERGE_DICT policy should merge metadata, not replace
        assert merged.metadata.final_outcome == "INCOMPLETE"
        assert merged.metadata.plan_progress is not None
        assert merged.metadata.plan_progress.completed_steps == 5

    def test_merge_updates_max_supervisor_steps(self):
        old = BlackboardState(
            metadata=BlackboardMetadata(max_supervisor_steps=20)
        )
        new = BlackboardState(
            metadata=BlackboardMetadata(max_supervisor_steps=50)
        )
        merged = merge_blackboard(old, new)
        assert merged.metadata.max_supervisor_steps == 50

    def test_merge_does_not_wipe_existing_progress(self):
        """Critical: merging a new blackboard without plan_progress
        should NOT wipe the existing plan_progress."""
        old = BlackboardState(
            metadata=BlackboardMetadata(
                plan_progress=PlanProgress(total_steps=10, completed_steps=7)
            )
        )
        new = BlackboardState(
            metadata=BlackboardMetadata(
                final_outcome="INCOMPLETE"
            )
        )
        merged = merge_blackboard(old, new)
        assert merged.metadata.plan_progress is not None
        assert merged.metadata.plan_progress.completed_steps == 7

    def test_merge_with_none_values(self):
        """None values in new metadata should not overwrite existing values."""
        old = BlackboardState(
            metadata=BlackboardMetadata(
                max_supervisor_steps=50,
                plan_progress=PlanProgress(total_steps=5, completed_steps=3),
            )
        )
        new = BlackboardState(
            metadata=BlackboardMetadata()
        )
        merged = merge_blackboard(old, new)
        assert merged.metadata.max_supervisor_steps == 50
        assert merged.metadata.plan_progress.completed_steps == 3


class TestBlackboardSerialization:
    """Tests for blackboard dict serialization round-trip."""

    def test_plan_progress_round_trip(self):
        original = BlackboardState(
            metadata=BlackboardMetadata(
                plan_progress=PlanProgress(total_steps=15, completed_steps=10, plan_id="abc")
            )
        )
        data = original.model_dump(mode="json")
        restored = BlackboardState.model_validate(data)
        assert restored.metadata.plan_progress.total_steps == 15
        assert restored.metadata.plan_progress.completed_steps == 10
        assert restored.metadata.plan_progress.plan_id == "abc"

    def test_max_supervisor_steps_round_trip(self):
        original = BlackboardState(
            metadata=BlackboardMetadata(max_supervisor_steps=75)
        )
        data = original.model_dump(mode="json")
        restored = BlackboardState.model_validate(data)
        assert restored.metadata.max_supervisor_steps == 75
