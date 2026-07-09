"""
End-to-end tests for thinking storage → extraction → fold → API pipeline.

Validates the simplified string-based thinking flow after removing list wrapping.
"""
import pytest
from app.core.engine.message.native_classes import AIMessage

from app.core.engine.message.mapper import BlockMapper
from app.core.engine.message.utils import to_base_message
from app.core.engine.message.schemas import MessageBlock
from app.core.engine.message.reasoning import extract_reasoning_from_kwargs


from app.models import Message as DBMessage


def _make_db_msg(**kwargs) -> DBMessage:
    """Helper to create a detached ORM Message for testing."""
    msg = DBMessage()
    for k, v in kwargs.items():
        setattr(msg, k, v)
    return msg


class TestToDb:
    """MessageBlock → DB dict"""

    def test_thinking_is_plain_string(self):
        block = MessageBlock(
            id="msg-test-1",
            thread_id="t1",
            role="ai",
            content="final answer",
            thinking="分析中...",
        )
        db_dict = BlockMapper.to_db(block)
        assert db_dict["thinking"] == "分析中..."
        assert isinstance(db_dict["thinking"], str)

    def test_thinking_none(self):
        block = MessageBlock(id="msg-test-2", thread_id="t1", role="ai", content="hi")
        db_dict = BlockMapper.to_db(block)
        assert db_dict["thinking"] is None


class TestFromDb:
    """DB ORM → MessageBlock"""

    def test_thinking_passthrough_string(self):
        db_msg = _make_db_msg(
            id="uuid-1",
            thread_id="t1",
            project_id=None,
            role="ai",
            content="final answer",
            thinking="分析中...",
            sequence_number=1,
            run_id="run-1",
            status="completed",
            category="assistant_response",
            content_type="text",
            is_visible=True,
            tool_calls=None,
            tool_call_id=None,
            tool_name=None,
            meta_data=None,
            checkpoint_id=None,
            parent_id=None,
            created_at=None,
            references=[],
        )
        block = BlockMapper.from_db(db_msg)
        assert block.thinking == "分析中..."
        assert isinstance(block.thinking, str)

    def test_thinking_none(self):
        db_msg = _make_db_msg(
            id="uuid-2",
            thread_id="t1",
            project_id=None,
            role="ai",
            content="hi",
            thinking=None,
            sequence_number=2,
            run_id=None,
            status="completed",
            category="assistant_response",
            content_type="text",
            is_visible=True,
            tool_calls=None,
            tool_call_id=None,
            tool_name=None,
            meta_data=None,
            checkpoint_id=None,
            parent_id=None,
            created_at=None,
            references=[],
        )
        block = BlockMapper.from_db(db_msg)
        assert block.thinking is None


class TestToBaseMessage:
    """DB ORM → LangChain BaseMessage"""

    def test_thinking_in_additional_kwargs(self):
        db_msg = _make_db_msg(
            role="ai",
            content="hello",
            thinking="reasoning text",
            tool_calls=None,
            tool_name=None,
            tool_call_id=None,
            id="1",
        )
        msg = to_base_message(db_msg)
        assert isinstance(msg, AIMessage)
        assert msg.additional_kwargs["thinking"] == "reasoning text"

    def test_no_thinking(self):
        db_msg = _make_db_msg(
            role="ai",
            content="hello",
            thinking=None,
            tool_calls=None,
            tool_name=None,
            tool_call_id=None,
            id="1",
        )
        msg = to_base_message(db_msg)
        assert isinstance(msg, AIMessage)
        assert "thinking" not in msg.additional_kwargs


class TestExtractReasoningFromKwargs:
    """Core extraction priority logic."""

    def test_prefers_thinking_key(self):
        assert extract_reasoning_from_kwargs({"thinking": "hello"}) == "hello"

    def test_fallback_to_reasoning_content(self):
        assert extract_reasoning_from_kwargs({"reasoning_content": "world"}) == "world"

    def test_thinking_takes_precedence(self):
        assert extract_reasoning_from_kwargs({"thinking": "a", "reasoning_content": "b"}) == "a"

    def test_empty_dict(self):
        assert extract_reasoning_from_kwargs({}) is None

    def test_none_input(self):
        assert extract_reasoning_from_kwargs(None) is None

    def test_whitespace_only_returns_none(self):
        assert extract_reasoning_from_kwargs({"thinking": "   "}) is None


class TestInferActionType:
    """_infer_action_type after simplification."""

    def test_pure_thinking_is_thinking(self):
        block = MessageBlock(id="1", thread_id="t1", role="ai", content="", thinking="reasoning")
        from app.core.engine.message.mapper import _infer_action_type
        assert _infer_action_type(block) == "thinking"

    def test_text_with_thinking_is_text(self):
        block = MessageBlock(id="1", thread_id="t1", role="ai", content="answer", thinking="reasoning")
        from app.core.engine.message.mapper import _infer_action_type
        assert _infer_action_type(block) == "text"

    def test_tool_output(self):
        # _infer_action_type now only returns "tool_output" for role="tool"
        block = MessageBlock(id="1", thread_id="t1", role="tool", content="ok", thinking=None)
        from app.core.engine.message.mapper import _infer_action_type
        assert _infer_action_type(block) == "tool_output"
