import pytest
from pydantic import ValidationError

from app.core.engine.message.schemas import MessageBlock, ToolCall
from app.core.engine.state import AgentState


class TestStandardizationRegression:
    """
    Regression tests to ensure all core models are strictly typed and
    do not allow dynamic attribute access without proper definition.
    """

    def test_state_allows_extra_fields(self):
        """AgentState inherits DynamicBaseModel which allows extra fields."""
        state = AgentState(
            worker_outcome="SUCCESS",
            unexpected_field="allowed"
        )
        assert state.worker_outcome == "SUCCESS"
        assert state.unexpected_field == "allowed"

    def test_message_block_mapping(self):
        """Test MessageBlock validation and defaults."""
        block = MessageBlock(
            id="msg-1-1",
            thread_id="thread-1",
            role="ai",
            content="Hello"
        )
        assert block.role == "ai"
        assert block.content_type == "text"  # default

        # Ensure role validation
        with pytest.raises(ValidationError):
            MessageBlock(
                id="msg-1-2",
                thread_id="t1",
                role="invalid_role",  # type: ignore
                content="Err"
            )

    def test_tool_call_validation(self):
        """Test ToolCall structure."""
        tool = ToolCall(
            id="tool-1",
            name="read_file",
            args={"path": "test.py"}
        )
        assert tool.type == "tool_call"  # default
        assert tool.args["path"] == "test.py"
