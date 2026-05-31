"""
Tests for audit utility functions (tier classification removed).

Run with: pytest tests/test_finish_auditor.py -v
"""

from langchain_core.messages import AIMessage

from app.core.engine.services.audit_service import (
    _extract_final_summary,
    _extract_tool_usage,
)


class MockMessage(AIMessage):
    def __init__(self, content=None, tool_calls=None):
        normalized_calls = []
        for tc in tool_calls or []:
            if isinstance(tc, dict):
                normalized_calls.append({
                    "id": tc.get("id", "call-1"),
                    "name": tc.get("name", ""),
                    "args": tc.get("args", {}),
                    "type": "tool_call",
                })
            else:
                normalized_calls.append(tc)
        super().__init__(content=content or "", tool_calls=normalized_calls)


class TestExtractFinalSummary:
    def test_extracts_final_report_tag(self):
        msg = AIMessage(content="""
<evoloop_session_audit>
<evoloop_final_report>Completed the task successfully.</evoloop_final_report>
</evoloop_session_audit>
""")
        assert _extract_final_summary([msg]) == "Completed the task successfully."

    def test_falls_back_to_content(self):
        msg = AIMessage(content="Task done.")
        assert _extract_final_summary([msg]) == "Task done."

    def test_returns_last_ai_message(self):
        msgs = [
            AIMessage(content="First"),
            AIMessage(content="Second"),
        ]
        assert _extract_final_summary(msgs) == "Second"

    def test_returns_default_when_no_ai_message(self):
        assert _extract_final_summary([]) == "Task completed."


class TestExtractToolUsage:
    def test_returns_tool_usage(self):
        msg = MockMessage(tool_calls=[{"name": "read_file", "args": {"path": "/test.py"}}])
        result = _extract_tool_usage([msg])
        assert "read_file" in result
        assert "/test.py" in result

    def test_returns_default_when_no_tools(self):
        msg = MockMessage(content="Hello")
        assert _extract_tool_usage([msg]) == "No tools used."
