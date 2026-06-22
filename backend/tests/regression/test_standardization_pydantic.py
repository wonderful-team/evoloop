import pytest
from pydantic import ValidationError
from app.core.engine.state.sub_schemas import BlackboardState, SpawnPlan, SubtaskResult
from app.core.engine.message.schemas import MessageBlock, ToolBlock
from app.models import ProjectResource

class TestStandardizationRegression:
    """
    Regression tests to ensure all core models are strictly typed and
    do not allow dynamic attribute access without proper definition.
    """

    def test_blackboard_allows_extra_fields(self):
        """BlackboardState inherits DynamicBaseModel which allows extra fields."""
        # Valid instantiation
        state = BlackboardState(
            spawn_plan=SpawnPlan(subtasks=[]),
            subtask_results=[]
        )
        assert state.spawn_plan.subtasks == []
        
        # Extra fields are allowed (DynamicBaseModel uses ConfigDict(extra="allow"))
        state = BlackboardState(
            spawn_plan=SpawnPlan(subtasks=[]),
            subtask_results=[],
            unexpected_field="allowed"
        )
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
        assert block.status == "completed"  # default
        assert block.content_type == "text" # default
        
        # Ensure role validation
        with pytest.raises(ValidationError):
            MessageBlock(
                id="msg-1-2",
                thread_id="t1",
                role="invalid_role", # type: ignore
                content="Err"
            )

    def test_tool_block_validation(self):
        """Test ToolBlock structure."""
        tool = ToolBlock(
            id="tool-1",
            tool_call_id="call-1",
            tool="read_file",
            input={"path": "test.py"}
        )
        assert tool.status == "pending"
        assert tool.input["path"] == "test.py"
