import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.cache_services import ActivityStateService, ActivityState
from app.core.monitoring.activity import ActivityMonitor
from app.models import AgentActivity

@pytest.mark.asyncio
async def test_quota_exhausted_retention_in_state_service():
    """Test that ActivityStateService.end_run preserves 'quota_exhausted' and 'cancelled' statuses."""
    service = ActivityStateService()

    # Create a mock session context manager
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session_scope = MagicMock(return_value=mock_session)

    with patch.object(service, "_get_session_scope", return_value=mock_session_scope), \
         patch.object(service, "get_state", new_callable=AsyncMock) as mock_get_state:
        
        # Scenario 1: Pre-existing status is 'quota_exhausted'. Call end_run(status="failed").
        # It should preserve 'quota_exhausted'.
        mock_activity = AgentActivity(thread_id="thread-1", status="quota_exhausted")
        mock_session.get.return_value = mock_activity
        
        # mock_get_state should return a state reflecting the preserved status
        mock_get_state.return_value = ActivityState(status="quota_exhausted")

        result = await service.end_run(thread_id="thread-1", status="failed")

        assert mock_activity.status == "quota_exhausted"
        assert result.status == "quota_exhausted"
        mock_session.get.assert_called_with(AgentActivity, "thread-1")

        # Scenario 2: Pre-existing status is 'cancelled'. Call end_run(status="failed").
        # It should preserve 'cancelled'.
        mock_activity_cancelled = AgentActivity(thread_id="thread-1", status="cancelled")
        mock_session.get.return_value = mock_activity_cancelled
        mock_get_state.return_value = ActivityState(status="cancelled")

        result = await service.end_run(thread_id="thread-1", status="failed")

        assert mock_activity_cancelled.status == "cancelled"
        assert result.status == "cancelled"

        # Scenario 3: Pre-existing status is 'stopping'. Call end_run(status="failed").
        # It should change to 'cancelled'.
        mock_activity_stopping = AgentActivity(thread_id="thread-1", status="stopping")
        mock_session.get.return_value = mock_activity_stopping
        mock_get_state.return_value = ActivityState(status="cancelled")

        result = await service.end_run(thread_id="thread-1", status="failed")

        assert mock_activity_stopping.status == "cancelled"
        assert result.status == "cancelled"

        # Scenario 4: Pre-existing status is 'running'. Call end_run(status="failed").
        # It should overwrite with 'failed'.
        mock_activity_running = AgentActivity(thread_id="thread-1", status="running")
        mock_session.get.return_value = mock_activity_running
        mock_get_state.return_value = ActivityState(status="failed")

        result = await service.end_run(thread_id="thread-1", status="failed")

        assert mock_activity_running.status == "failed"
        assert result.status == "failed"

        # Scenario 5: Pre-existing status is 'failed'. Call end_run(status="done").
        # It should preserve 'failed' (terminal state protection).
        mock_activity_failed = AgentActivity(thread_id="thread-1", status="failed")
        mock_session.get.return_value = mock_activity_failed
        mock_get_state.return_value = ActivityState(status="failed")

        result = await service.end_run(thread_id="thread-1", status="done")

        assert mock_activity_failed.status == "failed"
        assert result.status == "failed"


@pytest.mark.asyncio
async def test_quota_exhausted_retention_in_activity_monitor():
    """Test that ActivityMonitor.end_run publishes the finalized/retained status (e.g. 'quota_exhausted') rather than the raw status parameter."""
    mock_state_service = AsyncMock()
    monitor = ActivityMonitor()
    monitor._state_service = mock_state_service

    # Mock end_run to return the state where status is 'quota_exhausted' (even though parameter status="failed")
    mock_state_service.end_run.return_value = ActivityState(status="quota_exhausted")

    with patch("app.core.engine.event.publishers.publish_agent_run_completed", new_callable=AsyncMock) as mock_publish_completed, \
         patch("app.core.monitoring.activity.system_bus", new_callable=AsyncMock) as mock_system_bus:
        
        result = await monitor.end_run(thread_id="thread-1", status="failed", run_id="run-1", task_type="agent")

        assert result.status == "quota_exhausted"

        # Verify that publish_agent_run_completed was called with status="quota_exhausted" instead of "failed"
        mock_publish_completed.assert_called_once_with(
            thread_id="thread-1",
            status="quota_exhausted",
            payload={"run_id": "run-1", "outcome": None, "task_type": "agent"}
        )

        # Verify that system_bus.publish was called with SystemStatusEvent(status="quota_exhausted")
        mock_system_bus.publish.assert_called_once()
        published_event = mock_system_bus.publish.call_args[0][0]
        assert published_event.status == "quota_exhausted"
        assert published_event.thread_id == "thread-1"
