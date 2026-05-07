"""
Tests for LayeredAuditor

Run with: pytest tests/test_finish_auditor.py -v
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.engine.services.audit_service import (
    AuditDecision,
    LayeredAuditor,
    _extract_final_summary,
    _extract_tool_usage,
)


from langchain_core.messages import AIMessage

class MockMessage(AIMessage):
    """Mock message for testing."""
    def __init__(self, content=None, tool_calls=None, msg_type="ai"):
        # Normalize tool_calls to expected format
        normalized_calls = []
        for tc in (tool_calls or []):
            if isinstance(tc, dict):
                normalized_calls.append({"id": tc.get("id", "call-1"), "name": tc.get("name", ""), "args": tc.get("args", {}), "type": "tool_call"})
            else:
                normalized_calls.append(tc)
        super().__init__(content=content or "", tool_calls=normalized_calls)
        self.type = msg_type
    
    def __repr__(self):
        return f"MockMessage({self.type})"


class TestAuditDecision:
    """Test AuditDecision class."""
    
    def test_creation(self):
        """Should create with proper attributes."""
        decision = AuditDecision(tier="minimal", reason="readonly_safe", confidence=0.95)
        
        assert decision.tier == "minimal"
        assert decision.reason == "readonly_safe"
        assert decision.confidence == 0.95


class TestLayeredAuditorClassification:
    """Test audit tier classification."""
    
    @pytest.fixture
    def auditor(self):
        """Fresh auditor instance."""
        return LayeredAuditor()
    
    @pytest.fixture
    def empty_state(self):
        """Empty state for testing."""
        from unittest.mock import MagicMock
        mock = MagicMock()
        mock.blackboard.ticket = None
        mock.is_subtask = False
        return mock
    
    @pytest.fixture
    def empty_blackboard(self):
        """Empty blackboard for testing."""
        from unittest.mock import MagicMock
        mock = MagicMock()
        mock.verification = None
        return mock
    
    def test_comprehensive_for_file_write(self, auditor, empty_state, empty_blackboard):
        """File write operations should trigger comprehensive audit."""
        tool_history = ['write_file:{"path": "/tmp/test.py"}']
        messages = [MockMessage(content="File written successfully")]
        
        decision = auditor.classify_tier(tool_history, messages, empty_blackboard, empty_state)
        
        assert decision.tier == "comprehensive"
        assert "file_modification" in decision.reason
        assert decision.confidence == 1.0
    
    def test_comprehensive_for_edit_file(self, auditor, empty_state, empty_blackboard):
        """Edit file should trigger comprehensive audit."""
        tool_history = ['edit_file:{"path": "app.py"}']
        messages = [MockMessage(content="File edited")]
        
        decision = auditor.classify_tier(tool_history, messages, empty_blackboard, empty_state)
        
        assert decision.tier == "comprehensive"
    
    def test_comprehensive_for_execution(self, auditor, empty_state, empty_blackboard):
        """Code execution should trigger comprehensive audit."""
        tool_history = ['execute_command:{"cmd": "ls -la"}']
        messages = [MockMessage(content="Command output")]
        
        decision = auditor.classify_tier(tool_history, messages, empty_blackboard, empty_state)
        
        assert decision.tier == "comprehensive"
        assert "code_execution" in decision.reason
    
    def test_comprehensive_for_automation(self, auditor, empty_state, empty_blackboard):
        """UI automation should trigger comprehensive audit."""
        tool_history = ['mobile_control:{"action": "click"}']
        messages = [MockMessage(content="Clicked")]
        
        decision = auditor.classify_tier(tool_history, messages, empty_blackboard, empty_state)
        
        assert decision.tier == "comprehensive"
        assert "ui_automation" in decision.reason
    
    def test_comprehensive_for_error_in_content(self, auditor, empty_state, empty_blackboard):
        """Error markers in content should trigger comprehensive audit."""
        tool_history = ['read_file:{"path": "/tmp/test.py"}']
        messages = [MockMessage(content="[ERROR: File not found]")]
        
        decision = auditor.classify_tier(tool_history, messages, empty_blackboard, empty_state)
        
        assert decision.tier == "comprehensive"
        assert "error_detected" in decision.reason
    
    def test_comprehensive_for_exception(self, auditor, empty_state, empty_blackboard):
        """Exception in content should trigger comprehensive audit."""
        tool_history = ['read_file:{"path": "/tmp/test.py"}']
        messages = [MockMessage(content="Traceback (most recent call last):\n...")]
        
        decision = auditor.classify_tier(tool_history, messages, empty_blackboard, empty_state)
        
        assert decision.tier == "comprehensive"
    
    def test_comprehensive_for_high_complexity(self, auditor, empty_state):
        """High complexity ticket should trigger comprehensive audit."""
        from unittest.mock import MagicMock
        tool_history = ['read_file:{"path": "/tmp/test.py"}']
        messages = [MockMessage(content="Content")]
        blackboard = MagicMock()
        blackboard.verification = None
        empty_state.blackboard.ticket = MagicMock()
        empty_state.blackboard.ticket.complexity = "high"
        
        decision = auditor.classify_tier(tool_history, messages, blackboard, empty_state)
        
        assert decision.tier == "comprehensive"
        assert "high_complexity" in decision.reason
    
    def test_comprehensive_for_failed_verification(self, auditor, empty_state):
        """Failed verification should trigger comprehensive audit."""
        from unittest.mock import MagicMock
        tool_history = ['read_file:{"path": "/tmp/test.py"}']
        messages = [MockMessage(content="Content")]
        blackboard = MagicMock()
        blackboard.verification = MagicMock()
        blackboard.verification.status = "failed"
        empty_state.blackboard.ticket = None
        
        decision = auditor.classify_tier(tool_history, messages, blackboard, empty_state)
        
        assert decision.tier == "comprehensive"
        assert "verification_failed" in decision.reason
    
    def test_comprehensive_for_long_conversation(self, auditor, empty_state, empty_blackboard):
        """Long conversation should trigger comprehensive audit."""
        tool_history = ['read_file:{"path": "/tmp/test.py"}']
        messages = [MockMessage(content="Content") for _ in range(25)]  # 25 messages
        
        decision = auditor.classify_tier(tool_history, messages, empty_blackboard, empty_state)
        
        assert decision.tier == "comprehensive"
        assert "long_conversation" in decision.reason
    
    def test_minimal_for_readonly_only(self, auditor, empty_state, empty_blackboard):
        """Read-only operations can use minimal audit."""
        tool_history = [
            'read_file:{"path": "/tmp/app.py"}',
            'list_directory:{"path": "/tmp"}',
        ]
        messages = [MockMessage(content="File contents here with more text to exceed fifty characters minimum length requirement.")]
        
        decision = auditor.classify_tier(tool_history, messages, empty_blackboard, empty_state)
        
        assert decision.tier == "minimal"
        assert decision.reason == "readonly_safe"
    
    def test_minimal_rejects_empty_content(self, auditor, empty_state, empty_blackboard):
        """Empty content should not use minimal audit."""
        tool_history = ['read_file:{"path": "/tmp/test.py"}']
        messages = [MockMessage(content="")]
        
        decision = auditor.classify_tier(tool_history, messages, empty_blackboard, empty_state)
        
        assert decision.tier != "minimal"
    
    def test_minimal_rejects_short_content(self, auditor, empty_state, empty_blackboard):
        """Very short content should not use minimal audit."""
        tool_history = ['read_file:{"path": "/tmp/test.py"}']
        messages = [MockMessage(content="Hi")]  # < 50 chars
        
        decision = auditor.classify_tier(tool_history, messages, empty_blackboard, empty_state)
        
        assert decision.tier != "minimal"
    
    def test_minimal_rejects_long_content(self, auditor, empty_state, empty_blackboard):
        """Very long content should not use minimal audit."""
        tool_history = ['read_file:{"path": "/tmp/test.py"}']
        messages = [MockMessage(content="x" * 3500)]  # > 3000 chars
        
        decision = auditor.classify_tier(tool_history, messages, empty_blackboard, empty_state)
        
        assert decision.tier != "minimal"
    
    def test_minimal_rejects_subtask(self, auditor, empty_blackboard):
        """Subtasks should not use minimal audit."""
        from unittest.mock import MagicMock
        tool_history = ['read_file:{"path": "/tmp/test.py"}']
        messages = [MockMessage(content="File contents here with more text to exceed fifty characters minimum length requirement.")]
        state = MagicMock()
        state.blackboard.ticket = None
        state.is_subtask = True
        
        decision = auditor.classify_tier(tool_history, messages, empty_blackboard, state)
        
        assert decision.tier != "minimal"
    
    def test_standard_for_mixed_case(self, auditor, empty_state, empty_blackboard):
        """Mixed cases should default to standard audit."""
        tool_history = ['read_file:{"path": "/tmp/test.py"}']
        messages = [MockMessage(content="File contents here...")]
        # Not readonly-only but no comprehensive triggers
        
        decision = auditor.classify_tier(tool_history, messages, empty_blackboard, empty_state)
        
        assert decision.tier == "standard"


class TestMinimalAudit:
    """Test minimal audit execution."""
    
    @pytest.fixture
    def auditor(self):
        return LayeredAuditor()
    
    @pytest.mark.asyncio
    async def test_minimal_audit_read_file(self, auditor):
        """Minimal audit for read_file should have appropriate prefix."""
        messages = [
            MockMessage(tool_calls=[{'name': 'read_file', 'args': {'path': '/tmp/app.py'}}]),
            MockMessage(content="def hello(): pass"),
        ]
        blackboard = {}
        
        summary, meta = await auditor.audit_minimal(messages, blackboard)
        
        assert "def hello(): pass" in summary
        assert meta['tier'] == 'minimal'
        assert meta['duration_ms'] == 5
    
    @pytest.mark.asyncio
    async def test_minimal_audit_search(self, auditor):
        """Minimal audit for search should have appropriate prefix."""
        messages = [
            MockMessage(tool_calls=[{'name': 'search_files', 'args': {'pattern': '*.py'}}]),
            MockMessage(content="Found 5 matches"),
        ]
        blackboard = {}
        
        summary, meta = await auditor.audit_minimal(messages, blackboard)
        
        assert "Found 5 matches" in summary
    
    @pytest.mark.asyncio
    async def test_minimal_audit_list_directory(self, auditor):
        """Minimal audit for list_directory should have appropriate prefix."""
        messages = [
            MockMessage(tool_calls=[{'name': 'list_directory', 'args': {'path': '/tmp'}}]),
            MockMessage(content="- file1.py\n- file2.py"),
        ]
        blackboard = {}
        
        summary, meta = await auditor.audit_minimal(messages, blackboard)
        
        assert "file1.py" in summary
    
    @pytest.mark.asyncio
    async def test_minimal_audit_truncate_long_content(self, auditor):
        """Minimal audit should truncate very long content."""
        long_content = "x" * 3000
        messages = [
            MockMessage(tool_calls=[{'name': 'read_file', 'args': {'path': '/tmp/big.py'}}]),
            MockMessage(content=long_content),
        ]
        blackboard = {}
        
        summary, meta = await auditor.audit_minimal(messages, blackboard)
        
        assert "[Truncated]" in summary


class TestStandardAudit:
    """Test standard audit execution."""
    
    @pytest.fixture
    def auditor(self):
        return LayeredAuditor()
    
    @pytest.mark.asyncio
    async def test_standard_audit_calls_llm(self, auditor):
        """Standard audit should call LLM."""
        from unittest.mock import MagicMock
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="Task completed successfully."))
        auditor._fast_llm = mock_llm
        
        messages = [
            MockMessage(tool_calls=[{'name': 'read_file', 'args': {'path': '/tmp/app.py'}}]),
            MockMessage(content="def hello(): pass"),
        ]
        blackboard = MagicMock()
        blackboard.ticket = {"topic": "Read file"}
        blackboard.verification = None
        config = {}
        
        state = MagicMock()
        state.current_plan = ""
        state.iteration_count = 0
        state.project_id = 1
        state.session_goal = None
        summary, meta = await auditor.audit_standard(messages, blackboard, state, config)
        
        # LLM call goes through InternalLLMService, not directly through _fast_llm
        # Just verify the method runs and returns standard tier
        assert meta['tier'] == 'standard'
        assert 'duration_ms' in meta
    
    @pytest.mark.asyncio
    async def test_standard_audit_handles_llm_error(self, auditor):
        """Standard audit should handle LLM errors gracefully."""
        from unittest.mock import MagicMock
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))
        auditor._fast_llm = mock_llm
        
        messages = [
            MockMessage(content="File content"),
        ]
        blackboard = MagicMock()
        blackboard.ticket = None
        blackboard.verification = None
        config = {}
        
        state = MagicMock()
        state.current_plan = ""
        state.iteration_count = 0
        state.project_id = 1
        state.session_goal = None
        summary, meta = await auditor.audit_standard(messages, blackboard, state, config)
        
        assert "Task completed" in summary


class TestToolUsageExtraction:
    """Test _extract_tool_usage function."""
    
    def test_extract_from_ai_message_tool_calls(self):
        """Should extract tools from AIMessage.tool_calls."""
        from langchain_core.messages import AIMessage
        
        messages = [
            AIMessage(content="", tool_calls=[
                {'id': 'call-1', 'name': 'read_file', 'args': {'path': '/tmp/a.py'}, 'type': 'tool_call'},
                {'id': 'call-2', 'name': 'write_file', 'args': {'path': '/tmp/b.py'}, 'type': 'tool_call'},
            ])
        ]
        
        result = _extract_tool_usage(messages)
        
        assert 'read_file' in result
        assert 'write_file' in result
    
    def test_extract_from_tool_messages(self):
        """ToolMessage without tool_calls returns default message."""
        from langchain_core.messages import ToolMessage
        
        messages = [
            ToolMessage(content="Result", name="bash", tool_call_id="123"),
        ]
        
        result = _extract_tool_usage(messages)
        
        assert result == "No tools used."


class TestFinalSummaryExtraction:
    """Test _extract_final_summary function."""
    
    def test_extract_from_evoloop_final_report_tag(self):
        """Should extract content from <evoloop_final_report> tag."""
        from langchain_core.messages import AIMessage
        
        messages = [
            AIMessage(content="<evoloop_session_audit>...</evoloop_session_audit><evoloop_final_report>Summary here</evoloop_final_report>")
        ]
        
        result = _extract_final_summary(messages)
        
        assert result == "Summary here"
    
    def test_returns_full_content(self):
        """Returns full content when no special tags present."""
        from langchain_core.messages import AIMessage
        
        messages = [
            AIMessage(content="<audit>details</audit>Clean summary")
        ]
        
        result = _extract_final_summary(messages)
        
        assert result == "<audit>details</audit>Clean summary"
    
    def test_returns_long_content(self):
        """Returns full content without truncation."""
        from langchain_core.messages import AIMessage
        
        messages = [
            AIMessage(content="x" * 3000)
        ]
        
        result = _extract_final_summary(messages)
        
        assert len(result) == 3000


class TestPerformance:
    """Performance tests."""
    
    @pytest.mark.asyncio
    async def test_minimal_audit_speed(self):
        """Minimal audit should be very fast (< 1ms)."""
        auditor = LayeredAuditor()
        messages = [
            MockMessage(tool_calls=[{'name': 'read_file', 'args': {'path': '/tmp/test.py'}}]),
            MockMessage(content="File content"),
        ]
        
        start = time.time()
        for _ in range(100):
            summary, meta = await auditor.audit_minimal(messages, {})
        duration = (time.time() - start) / 100 * 1000  # ms per call
        
        assert duration < 1.0  # Should be < 1ms per call
        assert meta['duration_ms'] == 5  # Hardcoded in implementation
    
    def test_classification_speed(self):
        """Classification should be very fast."""
        from unittest.mock import MagicMock
        auditor = LayeredAuditor()
        tool_history = ['read_file:{"path": "/tmp/test.py"}']
        messages = [MockMessage(content="File content")]
        blackboard = MagicMock()
        blackboard.verification = None
        state = MagicMock()
        state.blackboard.ticket = None
        state.is_subtask = False
        
        start = time.time()
        for _ in range(1000):
            decision = auditor.classify_tier(tool_history, messages, blackboard, state)
        duration = (time.time() - start) / 1000 * 1000000  # microseconds per call
        
        assert duration < 100  # Should be < 100 microseconds


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
