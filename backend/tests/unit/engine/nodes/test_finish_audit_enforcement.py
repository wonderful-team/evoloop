"""
Tests for Finish Node Audit Enforcement

Verifies that the Finish node routes back to SUPERVISOR when the audit
outcome is INCOMPLETE, preventing premature mission termination.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine.nodes.finish import FinishNode
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState
from app.core.engine.state.blackboard import BlackboardState, BlackboardMetadata


class TestFinishAuditEnforcement:
    """Tests for the INCOMPLETE audit outcome routing."""

    @pytest.fixture
    def finish_node(self):
        return FinishNode()

    @pytest.fixture
    def config(self):
        return RunnableConfig(configurable={"thread_id": "test-thread", "model": "test-model"})

    def _make_state_with_outcome(self, outcome_text: str) -> AgentState:
        """Helper to create a state with an audit outcome in messages."""
        content = f"Some audit text\n<evoloop_audit_outcome>{outcome_text}</evoloop_audit_outcome>\nMore text"
        msg = AIMessage(content=content)
        blackboard = BlackboardState(metadata=BlackboardMetadata())
        return AgentState(
            messages=[msg],
            blackboard=blackboard,
        )

    @pytest.mark.asyncio
    async def test_incomplete_outcome_routes_to_supervisor(self, finish_node, config):
        """INCOMPLETE audit outcome must route to SUPERVISOR, not END."""
        state = self._make_state_with_outcome("INCOMPLETE")

        # Mock AuditService.execute to avoid real LLM calls
        mock_service = MagicMock()
        mock_service.execute = AsyncMock(return_value=MagicMock(
            tier="minimal",
            summary="",
            messages=[],
            blackboard=None,
            meta={"tier": "minimal"},
        ))
        finish_node._audit_service = mock_service

        result = await finish_node(state, config)

        assert result.next_node == RoutingTarget.SUPERVISOR
        # Verify the blackboard was updated
        bb = BlackboardState.model_validate(result.blackboard)
        assert bb.metadata.final_outcome == "INCOMPLETE"
        assert bb.worker_outcome == "incomplete"

    @pytest.mark.asyncio
    async def test_complete_outcome_routes_to_end(self, finish_node, config):
        """COMPLETE audit outcome should route to END normally."""
        state = self._make_state_with_outcome("COMPLETE")

        mock_service = MagicMock()
        mock_service.execute = AsyncMock(return_value=MagicMock(
            tier="minimal",
            summary="",
            messages=[],
            blackboard=None,
            meta={"tier": "minimal"},
        ))
        finish_node._audit_service = mock_service

        result = await finish_node(state, config)

        assert result.next_node == RoutingTarget.END
        bb = BlackboardState.model_validate(result.blackboard)
        assert bb.metadata.final_outcome == "COMPLETE"

    @pytest.mark.asyncio
    async def test_no_outcome_tag_routes_to_end(self, finish_node, config):
        """When no outcome tag is present, default to END."""
        msg = AIMessage(content="Just a normal finish message without any outcome tag.")
        blackboard = BlackboardState(metadata=BlackboardMetadata())
        state = AgentState(messages=[msg], blackboard=blackboard)

        mock_service = MagicMock()
        mock_service.execute = AsyncMock(return_value=MagicMock(
            tier="minimal",
            summary="",
            messages=[],
            blackboard=None,
            meta={"tier": "minimal"},
        ))
        finish_node._audit_service = mock_service

        result = await finish_node(state, config)

        assert result.next_node == RoutingTarget.END

    @pytest.mark.asyncio
    async def test_blocked_by_hook_overrides_incomplete(self, finish_node, config):
        """If blocked_by_hook is True, it should still route to SUPERVISOR."""
        content = "<evoloop_audit_outcome>INCOMPLETE</evoloop_audit_outcome>"
        msg = AIMessage(content=content)
        blackboard = BlackboardState(
            metadata=BlackboardMetadata(blocked_by_hook=True)
        )
        state = AgentState(messages=[msg], blackboard=blackboard)

        mock_service = MagicMock()
        mock_service.execute = AsyncMock(return_value=MagicMock(
            tier="minimal",
            summary="",
            messages=[],
            blackboard=None,
            meta={"tier": "minimal"},
        ))
        finish_node._audit_service = mock_service

        result = await finish_node(state, config)

        # FinishNode itself checks INCOMPLETE first, so it routes to SUPERVISOR.
        # route_finish also checks blocked_by_hook first, so either way it's SUPERVISOR.
        assert result.next_node == RoutingTarget.SUPERVISOR

    @pytest.mark.asyncio
    async def test_case_insensitive_incomplete(self, finish_node, config):
        """Outcome matching should be case-insensitive."""
        for variant in ["incomplete", "Incomplete", "INCOMPLETE", "InCoMpLeTe"]:
            state = self._make_state_with_outcome(variant)

            mock_service = MagicMock()
            mock_service.execute = AsyncMock(return_value=MagicMock(
                tier="minimal",
                summary="",
                messages=[],
                blackboard=None,
                meta={"tier": "minimal"},
            ))
            finish_node._audit_service = mock_service

            result = await finish_node(state, config)

            assert result.next_node == RoutingTarget.SUPERVISOR, f"Failed for variant: {variant}"
