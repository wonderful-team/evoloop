"""
Unit tests for PlanRewind event subscriber.
"""

from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.engine.rewind.event import RewindEventType, RewindRequestedEvent
from app.domain.planning.event.subscribers import PlanRewind
from app.models.planning import Plan as DBPlan
from app.models.planning import PlanStep as DBPlanStep


class TestPlanRewind:
    """Test cases for PlanRewind subscriber."""

    @pytest.fixture
    def mock_event_bus(self):
        """Create a mock event bus."""
        bus = MagicMock()
        bus.subscribe = MagicMock()
        return bus

    @pytest.fixture
    def plan_rewind(self):
        """Create a PlanRewind instance."""
        return PlanRewind()

    def test_register_subscribes_to_events(self, mock_event_bus, plan_rewind):
        """Test that register subscribes to correct events."""
        from app.core.events.decorators import register_instance_handlers
        register_instance_handlers(plan_rewind, mock_event_bus)

        # Check subscription
        mock_event_bus.subscribe.assert_called_once()
        call = mock_event_bus.subscribe.call_args
        assert call[0][0] == RewindEventType.REWIND_REQUESTED

    @pytest.mark.asyncio
    @patch("app.core.events.system_bus.publish")
    @patch("app.domain.planning.event.subscribers.session_scope")
    async def test_handle_rewind_deletes_plan_created_after_rewind(
        self, mock_session_scope, mock_system_bus_publish, plan_rewind
    ):
        """Test that a plan created after the rewind target is deleted."""
        # Arrange
        target_time = datetime(2026, 6, 22, 10, 0, 0, tzinfo=timezone.utc)
        plan_time = datetime(2026, 6, 22, 10, 5, 0, tzinfo=timezone.utc)

        # Mock target message timestamp query
        mock_session = AsyncMock()
        mock_session.scalar = AsyncMock(return_value=target_time)

        # Mock plan query
        mock_plan = DBPlan(
            id="plan-123",
            thread_id="thread-123",
            created_at=plan_time,
        )
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_plan))
        )

        async_mock = MagicMock()
        async_mock.__aenter__ = AsyncMock(return_value=mock_session)
        async_mock.__aexit__ = AsyncMock(return_value=False)
        mock_session_scope.return_value = async_mock

        event = RewindRequestedEvent(
            thread_id="thread-123",
            target_sequence=5,
            affected_run_ids=["run-123"],
            results={},
            errors=[],
        )

        # Act
        await plan_rewind._handle_rewind_requested(event)

        # Assert
        mock_session.delete.assert_called_once_with(mock_plan)
        assert event.results.get("plans") == 1
        
        # Verify event was published for deletion
        mock_system_bus_publish.assert_called_once()
        published_event = mock_system_bus_publish.call_args[0][0]
        from app.domain.planning.event import PlanUpdatedEvent
        assert isinstance(published_event, PlanUpdatedEvent)
        assert published_event.thread_id == "thread-123"
        assert published_event.plan_id == "plan-123"
        assert published_event.status == "deleted"

    @pytest.mark.asyncio
    @patch("app.core.events.system_bus.publish")
    @patch("app.domain.planning.event.subscribers.session_scope")
    async def test_handle_rewind_resets_stale_steps(
        self, mock_session_scope, mock_system_bus_publish, plan_rewind
    ):
        """Test that stale steps are reset and the first pending step becomes in_progress."""
        # Arrange
        target_time = datetime(2026, 6, 22, 10, 0, 0, tzinfo=timezone.utc)
        plan_time = datetime(2026, 6, 22, 9, 0, 0, tzinfo=timezone.utc)

        # Mock target message timestamp query
        mock_session = AsyncMock()
        mock_session.scalar = AsyncMock(return_value=target_time)

        # Mock plan query
        mock_plan = DBPlan(
            id="plan-123",
            thread_id="thread-123",
            created_at=plan_time,
        )
        
        # Mock steps
        step_0 = DBPlanStep(id="step-0", plan_id="plan-123", status="completed", order=0, execution_run_id="run-completed", updated_at=datetime(2026, 6, 22, 9, 30, 0, tzinfo=timezone.utc))
        step_1 = DBPlanStep(id="step-1", plan_id="plan-123", status="completed", order=1, execution_run_id="run-affected", updated_at=datetime(2026, 6, 22, 10, 5, 0, tzinfo=timezone.utc))
        step_2 = DBPlanStep(id="step-2", plan_id="plan-123", status="in_progress", order=2, execution_run_id="run-affected", updated_at=datetime(2026, 6, 22, 10, 10, 0, tzinfo=timezone.utc))
        step_3 = DBPlanStep(id="step-3", plan_id="plan-123", status="pending", order=3, execution_run_id=None, updated_at=datetime(2026, 6, 22, 9, 15, 0, tzinfo=timezone.utc))

        
        # Mock executing queries
        mock_session.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_plan)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[step_0, step_1, step_2, step_3]))))
        ])

        async_mock = MagicMock()
        async_mock.__aenter__ = AsyncMock(return_value=mock_session)
        async_mock.__aexit__ = AsyncMock(return_value=False)
        mock_session_scope.return_value = async_mock

        event = RewindRequestedEvent(
            thread_id="thread-123",
            target_sequence=5,
            affected_run_ids=["run-affected"],
            results={},
            errors=[],
        )

        # Act
        await plan_rewind._handle_rewind_requested(event)

        # Assert
        # Step 0: not affected (different run_id, not stale) -> remains completed
        assert step_0.status == "completed"

        # Step 1: affected -> execution_run_id is reset, result reset, status becomes pending,
        # but since it's the lowest order non-completed step, it should become in_progress!
        assert step_1.status == "in_progress"
        assert step_1.execution_run_id is None
        assert step_1.result is None

        # Step 2: affected -> execution_run_id reset, status becomes pending (since step 1 takes in_progress)
        assert step_2.status == "pending"
        assert step_2.execution_run_id is None

        # Step 3: was pending, not affected -> remains pending
        assert step_3.status == "pending"

        assert event.results.get("plans") == 2
        
        # Verify event was published for update
        mock_system_bus_publish.assert_called_once()
        published_event = mock_system_bus_publish.call_args[0][0]
        from app.domain.planning.event import PlanUpdatedEvent
        assert isinstance(published_event, PlanUpdatedEvent)
        assert published_event.thread_id == "thread-123"
        assert published_event.plan_id == "plan-123"
        assert published_event.status is None
