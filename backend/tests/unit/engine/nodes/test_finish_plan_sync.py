"""
Tests for FinishNode._sync_plan_progress_from_db

Verifies that plan_progress is synced from the database when not present
in the blackboard metadata.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from langchain_core.runnables import RunnableConfig

from app.core.engine.nodes.finish import FinishNode
from app.core.engine.state import AgentState
from app.core.engine.state.blackboard import BlackboardState, BlackboardMetadata, PlanProgress


class TestFinishPlanSync:
    """Tests for plan_progress sync from DB."""

    @pytest.fixture
    def finish_node(self):
        return FinishNode()

    @pytest.fixture
    def config(self):
        return RunnableConfig(configurable={"thread_id": "test-thread", "model": "test-model"})

    @pytest.mark.asyncio
    async def test_sync_plan_progress_when_empty(self, finish_node, config):
        """When plan_progress is None, it should be synced from DB."""
        metadata = BlackboardMetadata()
        assert metadata.plan_progress is None

        blackboard = BlackboardState(metadata=metadata)
        state = AgentState(
            thread_id="test-thread",
            messages=[],
            blackboard=blackboard,
        )

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = {"total": 2, "completed": 1, "plan_id": "plan-123"}
            await finish_node._sync_plan_progress_from_db(state, blackboard)

        assert metadata.plan_progress is not None
        assert metadata.plan_progress.total_steps == 2
        assert metadata.plan_progress.completed_steps == 1
        assert metadata.plan_progress.plan_id == "plan-123"

    @pytest.mark.asyncio
    async def test_re_sync_when_plan_progress_exists(self, finish_node, config):
        """When plan_progress already exists, re-sync from DB to get latest state."""
        metadata = BlackboardMetadata(
            plan_progress=PlanProgress(total_steps=10, completed_steps=5, plan_id="existing")
        )
        blackboard = BlackboardState(metadata=metadata)
        state = AgentState(
            thread_id="test-thread",
            messages=[],
            blackboard=blackboard,
        )

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = {"total": 20, "completed": 15, "plan_id": "updated"}
            await finish_node._sync_plan_progress_from_db(state, blackboard)
            mock_to_thread.assert_called_once()

        assert metadata.plan_progress.total_steps == 20
        assert metadata.plan_progress.completed_steps == 15
        assert metadata.plan_progress.plan_id == "updated"

    @pytest.mark.asyncio
    async def test_skip_sync_when_no_thread_id(self, finish_node, config):
        """When thread_id is missing, skip DB sync gracefully."""
        metadata = BlackboardMetadata()
        blackboard = BlackboardState(metadata=metadata)
        state = AgentState(
            thread_id=None,
            messages=[],
            blackboard=blackboard,
        )

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            await finish_node._sync_plan_progress_from_db(state, blackboard)
            mock_to_thread.assert_not_called()

        assert metadata.plan_progress is None

    @pytest.mark.asyncio
    async def test_skip_sync_when_no_plan_in_db(self, finish_node, config):
        """When no plan exists in DB, skip gracefully."""
        metadata = BlackboardMetadata()
        blackboard = BlackboardState(metadata=metadata)
        state = AgentState(
            thread_id="test-thread",
            messages=[],
            blackboard=blackboard,
        )

        with patch("app.infrastructure.database.sql.database.session_scope") as mock_session_scope:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none = MagicMock(return_value=None)
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            await finish_node._sync_plan_progress_from_db(state, blackboard)

        assert metadata.plan_progress is None
