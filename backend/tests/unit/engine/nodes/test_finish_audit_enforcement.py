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

        # Outcome tag comes from comprehensive audit result messages
        outcome_msg = AIMessage(
            content="Audit review complete.\n<evoloop_audit_outcome>INCOMPLETE</evoloop_audit_outcome>"
        )
        mock_service = MagicMock()
        mock_service.execute = AsyncMock(return_value=MagicMock(
            tier="comprehensive",
            summary="Task incomplete.",
            messages=[outcome_msg],
            blackboard=None,
            meta={"tier": "comprehensive"},
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

        outcome_msg = AIMessage(
            content="Audit review complete.\n<evoloop_audit_outcome>COMPLETE</evoloop_audit_outcome>"
        )
        mock_service = MagicMock()
        mock_service.execute = AsyncMock(return_value=MagicMock(
            tier="comprehensive",
            summary="Task complete.",
            messages=[outcome_msg],
            blackboard=None,
            meta={"tier": "comprehensive"},
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
        """INCOMPLETE outcome routes to SUPERVISOR even with blocked_by_hook flag set."""
        content = "<evoloop_audit_outcome>INCOMPLETE</evoloop_audit_outcome>"
        msg = AIMessage(content=content)
        blackboard = BlackboardState(
            metadata=BlackboardMetadata(blocked_by_hook=True)
        )
        state = AgentState(messages=[msg], blackboard=blackboard)

        outcome_msg = AIMessage(content=content)
        mock_service = MagicMock()
        mock_service.execute = AsyncMock(return_value=MagicMock(
            tier="comprehensive",
            summary="",
            messages=[outcome_msg],
            blackboard=None,
            meta={"tier": "comprehensive"},
        ))
        finish_node._audit_service = mock_service

        result = await finish_node(state, config)

        # FinishNode checks INCOMPLETE first and routes to SUPERVISOR
        assert result.next_node == RoutingTarget.SUPERVISOR

    @pytest.mark.asyncio
    async def test_case_insensitive_incomplete(self, finish_node, config):
        """Outcome matching should be case-insensitive."""
        for variant in ["incomplete", "Incomplete", "INCOMPLETE", "InCoMpLeTe"]:
            state = self._make_state_with_outcome(variant)

            outcome_msg = AIMessage(
                content=f"<evoloop_audit_outcome>{variant}</evoloop_audit_outcome>"
            )
            mock_service = MagicMock()
            mock_service.execute = AsyncMock(return_value=MagicMock(
                tier="comprehensive",
                summary="",
                messages=[outcome_msg],
                blackboard=None,
                meta={"tier": "comprehensive"},
            ))
            finish_node._audit_service = mock_service

            result = await finish_node(state, config)

            assert result.next_node == RoutingTarget.SUPERVISOR, f"Failed for variant: {variant}"
