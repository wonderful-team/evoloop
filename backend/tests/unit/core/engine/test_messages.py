"""
Unit tests for Message domain model.

Tests for the Message, ToolCall, and MessageList classes that provide
type-safe message handling over LangChain messages.

pytest tests/unit/core/engine/test_messages.py -v
"""

from app.core.engine.messages import (
    Message,
    MessageList,
    ToolCall,
    ToolExtractor,
)
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)


class TestToolCall:
    """Test ToolCall dataclass."""

    def test_from_raw_dict(self):
        raw = {"name": "read_file", "args": {"path": "/test"}, "id": "call_123"}
        tc = ToolCall.from_raw(raw)
        assert tc.name == "read_file"
        assert tc.args == {"path": "/test"}
        assert tc.id == "call_123"

    def test_from_raw_object(self):
        class MockToolCall:
            name = "edit_file"
            args = {"path": "/test", "content": "hello"}
            id = "call_456"

        tc = ToolCall.from_raw(MockToolCall())
        assert tc.name == "edit_file"
        assert tc.args == {"path": "/test", "content": "hello"}

    def test_to_dict(self):
        tc = ToolCall(name="search", args={"query": "test"}, id="call_789")
        d = tc.to_dict()
        assert d == {"name": "search", "args": {"query": "test"}, "id": "call_789"}


class TestMessage:
    """Test Message domain model."""

    def test_from_ai_message(self):
        lc_msg = AIMessage(
            content="Hello",
            tool_calls=[{"name": "read_file", "args": {}, "id": "call_1"}],
            response_metadata={"key": "value"},
        )
        msg = Message.from_lc(lc_msg)

        assert msg.role == "ai"
        assert msg.content == "Hello"
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "read_file"
        assert msg.metadata == {"key": "value"}

    def test_from_tool_message(self):
        lc_msg = ToolMessage(
            content="File contents",
            tool_call_id="call_1",
            name="read_file",
        )
        msg = Message.from_lc(lc_msg)

        assert msg.role == "tool"
        assert msg.content == "File contents"
        assert msg.tool_call_id == "call_1"
        assert msg.name == "read_file"

    def test_from_human_message(self):
        lc_msg = HumanMessage(content="Please help me")
        msg = Message.from_lc(lc_msg)

        assert msg.role == "human"
        assert msg.content == "Please help me"

    def test_from_system_message(self):
        lc_msg = SystemMessage(content="You are a helpful assistant")
        msg = Message.from_lc(lc_msg)

        assert msg.role == "system"
        assert msg.content == "You are a helpful assistant"

    def test_role_properties(self):
        msg = Message(role="ai", content="test")
        assert msg.is_ai is True
        assert msg.is_tool is False
        assert msg.is_human is False
        assert msg.is_system is False

    def test_has_tool_calls(self):
        msg_with = Message(role="ai", content="test", tool_calls=[ToolCall(name="test", args={})])
        msg_without = Message(role="ai", content="test")

        assert msg_with.has_tool_calls is True
        assert msg_without.has_tool_calls is False

    def test_is_error(self):
        error_msg = Message(role="ai", content="error", metadata={"is_error": True})
        normal_msg = Message(role="ai", content="normal")

        assert error_msg.is_error is True
        assert normal_msg.is_error is False

    def test_get_tool_names(self):
        msg = Message(
            role="ai",
            content="test",
            tool_calls=[
                ToolCall(name="read_file", args={}),
                ToolCall(name="edit_file", args={}),
            ]
        )
        assert msg.get_tool_names() == {"read_file", "edit_file"}

    def test_with_metadata(self):
        msg = Message(role="ai", content="test", metadata={"original": True})
        new_msg = msg.with_metadata(added="value")

        assert new_msg.metadata == {"original": True, "added": "value"}
        # Original unchanged
        assert msg.metadata == {"original": True}

    def test_roundtrip_conversion(self):
        original = AIMessage(
            content="Test",
            tool_calls=[{"name": "tool", "args": {}, "id": "123"}],
            metadata={"key": "value"},
            id="msg_123",
        )
        domain = Message.from_lc(original)
        converted = domain.to_lc()

        assert isinstance(converted, AIMessage)
        assert converted.content == "Test"
        assert len(converted.tool_calls) == 1


class TestMessageList:
    """Test MessageList container."""

    def test_from_lc(self):
        lc_messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there"),
            ToolMessage(content="Result", tool_call_id="call_1", name="tool"),
        ]
        msg_list = MessageList.from_lc(lc_messages)

        assert len(msg_list) == 3
        assert msg_list[0].role == "human"
        assert msg_list[1].role == "ai"
        assert msg_list[2].role == "tool"

    def test_role_filters(self):
        msg_list = MessageList([
            Message(role="human", content="1"),
            Message(role="ai", content="2"),
            Message(role="tool", content="3"),
            Message(role="ai", content="4"),
        ])

        assert len(msg_list.human_messages) == 1
        assert len(msg_list.ai_messages) == 2
        assert len(msg_list.tool_messages) == 1

    def test_get_last_ai(self):
        msg_list = MessageList([
            Message(role="human", content="1"),
            Message(role="ai", content="2"),
            Message(role="tool", content="3"),
            Message(role="ai", content="4"),
        ])

        last_ai = msg_list.get_last_ai()
        assert last_ai is not None
        assert last_ai.content == "4"

    def test_get_last_ai_none(self):
        msg_list = MessageList([
            Message(role="human", content="1"),
            Message(role="tool", content="2"),
        ])

        assert msg_list.get_last_ai() is None

    def test_get_tool_usage(self):
        msg_list = MessageList([
            Message(role="ai", content="1", tool_calls=[ToolCall(name="tool_a", args={})]),
            Message(role="tool", content="2", name="tool_b"),
            Message(role="ai", content="3", tool_calls=[ToolCall(name="tool_c", args={})]),
        ])

        tools = msg_list.get_tool_usage()
        assert tools == {"tool_a", "tool_b", "tool_c"}

    def test_get_text_content(self):
        msg_list = MessageList([
            Message(role="human", content="Hello"),
            Message(role="ai", content="World"),
            Message(role="system", content="!"),
        ])

        text = msg_list.get_text_content()
        assert "Hello" in text
        assert "World" in text
        assert "!" in text


class TestToolExtractor:
    """Test ToolExtractor visitor."""

    def test_extract_from_ai_and_tool(self):
        messages = [
            Message(role="ai", content="test", tool_calls=[ToolCall(name="read_file", args={})]),
            Message(role="tool", content="result", name="read_file"),
        ]
        extractor = ToolExtractor()
        extractor.visit_all(messages)

        assert extractor.get_tool_names() == {"read_file"}

    def test_extract_multiple(self):
        messages = [
            Message(role="ai", content="test", tool_calls=[
                ToolCall(name="read_file", args={}),
                ToolCall(name="edit_file", args={}),
            ]),
            Message(role="tool", content="r1", name="read_file"),
            Message(role="tool", content="r2", name="edit_file"),
        ]
        extractor = ToolExtractor()
        extractor.visit_all(messages)

        assert extractor.get_tool_names() == {"read_file", "edit_file"}

    def test_ignore_non_tool_messages(self):
        messages = [
            Message(role="human", content="Hello"),
            Message(role="ai", content="Hi"),
            Message(role="system", content="You are helpful"),
        ]
        extractor = ToolExtractor()
        extractor.visit_all(messages)

        assert extractor.get_tool_names() == set()
