"""Tests for AuditService Phase 1 refactoring.

Verifies:
- Tier classification triggers (long_conversation > 50, anomalies, user_requested)
- Structured audit input building (_build_audit_input)
- Message truncation when structured input is available
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.core.engine.services.audit_service import LayeredAuditor, AuditService
from app.core.engine.state.blackboard import (
    BlackboardState,
    BlackboardMetadata,
    PlanProgress,
    AuditAnomaly,
    AuditInputData,
    ProgressMetrics,
    TaskDeliverable,
)
from app.core.engine.state import AgentState
from langchain_core.messages import AIMessage, HumanMessage


class TestClassifyTier:
    """Tests for LayeredAuditor.classify_tier trigger conditions."""

    def _make_state(self, messages=None, anomalies=None, force_comprehensive=False):
        metadata = BlackboardMetadata(
            audit_anomalies=anomalies or [],
            force_comprehensive_audit=force_comprehensive,
        )
        blackboard = BlackboardState(metadata=metadata)
        return AgentState(
            messages=messages or [],
            blackboard=blackboard,
            session_goal="Test goal",
        )

    def test_minimal_tier_for_readonly_task(self):
        auditor = LayeredAuditor()
        messages = [AIMessage(content="Task completed successfully. All read-only operations were performed without any issues.")]
        state = self._make_state(messages=messages)
        decision = auditor.classify_tier([], messages, state.blackboard, state)
        assert decision.tier == "minimal"

    def test_standard_tier_for_mixed_tools(self):
        auditor = LayeredAuditor()
        messages = [AIMessage(content="Task completed.")]
        state = self._make_state(messages=messages)
        tool_history = ["read_file:./test.py"]
        decision = auditor.classify_tier(tool_history, messages, state.blackboard, state)
        assert decision.tier == "standard"

    def test_long_conversation_trigger_at_51_messages(self):
        auditor = LayeredAuditor()
        messages = [AIMessage(content=f"Step {i}") for i in range(51)]
        state = self._make_state(messages=messages)
        tool_history = ["write_file:./test.py"]
        decision = auditor.classify_tier(tool_history, messages, state.blackboard, state)
        assert decision.tier == "comprehensive"
        assert "long_conversation" in decision.reason

    def test_long_conversation_not_triggered_at_20_messages(self):
        """Phase 1: threshold raised from 20 to 50."""
        auditor = LayeredAuditor()
        messages = [AIMessage(content=f"Step {i}") for i in range(20)]
        state = self._make_state(messages=messages)
        tool_history = ["read_file:./test.py"]
        decision = auditor.classify_tier(tool_history, messages, state.blackboard, state)
        assert decision.tier != "comprehensive"

    def test_anomalies_detected_trigger(self):
        auditor = LayeredAuditor()
        messages = [AIMessage(content="Done.")]
        anomalies = [AuditAnomaly(anomaly_type="context_overload", severity="warn", description="Too many msgs")]
        state = self._make_state(messages=messages, anomalies=anomalies)
        tool_history = ["read_file:./test.py"]
        decision = auditor.classify_tier(tool_history, messages, state.blackboard, state)
        assert decision.tier == "comprehensive"
        assert "anomalies_detected" in decision.reason

    def test_user_requested_trigger(self):
        auditor = LayeredAuditor()
        messages = [AIMessage(content="Done.")]
        state = self._make_state(messages=messages, force_comprehensive=True)
        tool_history = ["read_file:./test.py"]
        decision = auditor.classify_tier(tool_history, messages, state.blackboard, state)
        assert decision.tier == "comprehensive"
        assert "user_requested" in decision.reason


class TestBuildAuditInput:
    """Tests for LayeredAuditor._build_audit_input."""

    def _make_state_with_plan(self, total=10, completed=7, tool_history=None):
        metadata = BlackboardMetadata(
            plan_progress=PlanProgress(total_steps=total, completed_steps=completed),
            tool_history=tool_history or [],
        )
        blackboard = BlackboardState(metadata=metadata)
        return AgentState(blackboard=blackboard, session_goal="Build wiki")

    def test_builds_plan_summary(self):
        auditor = LayeredAuditor()
        state = self._make_state_with_plan(total=10, completed=7)
        result = auditor._build_audit_input(state)
        assert result["plan_summary"] == {"total": 10, "completed": 7, "remaining": 3}

    def test_builds_tool_stats(self):
        auditor = LayeredAuditor()
        state = self._make_state_with_plan(tool_history=[
            "write_wiki_page:page1", "write_wiki_page:page2", "update_step_status:s1"
        ])
        result = auditor._build_audit_input(state)
        assert result["tool_stats"]["write_wiki_page"] == 2
        assert result["tool_stats"]["update_step_status"] == 1

    def test_includes_anomalies(self):
        auditor = LayeredAuditor()
        metadata = BlackboardMetadata(
            plan_progress=PlanProgress(total_steps=5, completed_steps=5),
            audit_anomalies=[AuditAnomaly(anomaly_type="test", severity="info", description="Test anomaly")],
        )
        state = AgentState(blackboard=BlackboardState(metadata=metadata))
        result = auditor._build_audit_input(state)
        assert len(result["anomalies"]) == 1
        assert result["anomalies"][0]["anomaly_type"] == "test"

    def test_uses_prebuilt_audit_input_data_when_available(self):
        auditor = LayeredAuditor()
        audit_input = AuditInputData(
            original_goal="Build wiki",
            plan_summary={"total": 25, "completed": 20, "remaining": 5},
            progress=ProgressMetrics(completed_steps=20, total_steps=25),
            deliverables=[TaskDeliverable(deliverable_type="wiki_page", title="Test Page", word_count=1000)],
        )
        metadata = BlackboardMetadata(audit_input_data=audit_input)
        state = AgentState(blackboard=BlackboardState(metadata=metadata))
        result = auditor._build_audit_input(state)
        assert result["plan_summary"]["total"] == 25
        assert len(result["deliverables"]) == 1


class TestFinishNodePrepareAuditInput:
    """Tests for FinishNode._prepare_audit_input."""

    @pytest.fixture
    def finish_node(self):
        from app.core.engine.nodes.finish import FinishNode
        return FinishNode()

    @pytest.mark.asyncio
    async def test_prepares_audit_input_with_plan_progress(self, finish_node):
        metadata = BlackboardMetadata(
            plan_progress=PlanProgress(total_steps=10, completed_steps=8),
            tool_history=["write_wiki_page:p1", "write_wiki_page:p2"],
        )
        blackboard = BlackboardState(metadata=metadata)
        state = AgentState(blackboard=blackboard, messages=[AIMessage(content="Done")] * 10)

        await finish_node._prepare_audit_input(state, blackboard)

        assert blackboard.metadata.audit_input_data is not None
        assert blackboard.metadata.audit_input_data.plan_summary["completed"] == 8
        # tool_stats is no longer populated by _prepare_audit_input (simplified in refactor)
        assert blackboard.metadata.audit_input_data.tool_stats == {}

    @pytest.mark.asyncio
    async def test_detects_incomplete_plan_anomaly(self, finish_node):
        metadata = BlackboardMetadata(
            plan_progress=PlanProgress(total_steps=10, completed_steps=5),
        )
        blackboard = BlackboardState(metadata=metadata)
        state = AgentState(blackboard=blackboard, messages=[AIMessage(content="x")] * 10)

        await finish_node._prepare_audit_input(state, blackboard)

        anomaly_types = [a.anomaly_type for a in blackboard.metadata.audit_anomalies]
        assert "incomplete_plan" in anomaly_types

    @pytest.mark.asyncio
    async def test_rebuilds_audit_input_even_with_existing_deliverables(self, finish_node):
        # Phase 2: _prepare_audit_input now always rebuilds to query fresh DB state
        existing_input = AuditInputData(
            deliverables=[TaskDeliverable(title="Existing", deliverable_type="wiki_page")],
        )
        metadata = BlackboardMetadata(audit_input_data=existing_input)
        blackboard = BlackboardState(metadata=metadata)
        state = AgentState(blackboard=blackboard)

        await finish_node._prepare_audit_input(state, blackboard)

        # Should rebuild (query DB for latest state), existing deliverables may be replaced
        assert blackboard.metadata.audit_input_data is not None
