"""Tests for BlockMapper.to_mobile() — specifically client_message_id passthrough."""

import pytest
from datetime import datetime
from app.core.engine.message.schemas import MessageBlock
from app.core.engine.message.mapper import BlockMapper


class TestToMobileClientMessageId:
    """to_mobile() should include client_message_id for human messages."""

    def test_human_message_includes_client_message_id(self):
        block = MessageBlock(
            id="human-uuid-123",
            thread_id="thread-1",
            role="human",
            content="Hello",
            created_at=datetime.now().isoformat(),
        )
        result = BlockMapper.to_mobile(block)
        assert result["client_message_id"] == "human-uuid-123"

    def test_ai_message_does_not_include_client_message_id(self):
        block = MessageBlock(
            id="ai-uuid-456",
            thread_id="thread-1",
            role="ai",
            content="Hello back",
            created_at=datetime.now().isoformat(),
        )
        result = BlockMapper.to_mobile(block)
        assert "client_message_id" not in result

    def test_tool_message_does_not_include_client_message_id(self):
        block = MessageBlock(
            id="tool-uuid-789",
            thread_id="thread-1",
            role="tool",
            content="result",
            created_at=datetime.now().isoformat(),
        )
        result = BlockMapper.to_mobile(block)
        assert "client_message_id" not in result

    def test_human_message_with_empty_id(self):
        block = MessageBlock(
            id="",
            thread_id="thread-1",
            role="human",
            content="Hello",
            created_at=datetime.now().isoformat(),
        )
        result = BlockMapper.to_mobile(block)
        assert "client_message_id" not in result

    def test_is_visible_conversion(self):
        block = MessageBlock(
            id="test-1",
            thread_id="thread-1",
            role="human",
            content="Hi",
            is_visible=True,
            created_at=datetime.now().isoformat(),
        )
        result = BlockMapper.to_mobile(block)
        assert result["is_visible"] == 1

        block.is_visible = False
        result = BlockMapper.to_mobile(block)
        assert result["is_visible"] == 0

    def test_created_at_conversion(self):
        block = MessageBlock(
            id="test-1",
            thread_id="thread-1",
            role="ai",
            content="Hello",
            created_at="2024-01-15T10:30:00+08:00",
        )
        result = BlockMapper.to_mobile(block)
        assert result["created_at"] == 1705285800
