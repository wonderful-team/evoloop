"""
测试 Message Persistence 和 Stream 策略
"""

import pytest
from app.core.messaging.category import MessageCategory
from app.core.messaging.persistence import MessagePersistencePolicy
from app.core.messaging.stream import MessageStreamPolicy


class TestMessagePersistencePolicy:
    """测试消息持久化策略"""
    
    def test_user_message_persistence(self):
        """测试 USER 消息持久化"""
        result = MessagePersistencePolicy.apply_policy(
            category=MessageCategory.USER,
            content="Hello"
        )
        assert result["should_persist"] is True
        assert result["content"] == "Hello"
        assert result["thinking"] is None
    
    def test_assistant_response_persistence(self):
        """测试 ASSISTANT_RESPONSE 持久化"""
        result = MessagePersistencePolicy.apply_policy(
            category=MessageCategory.ASSISTANT_RESPONSE,
            content="Reply"
        )
        assert result["should_persist"] is True
        assert result["content"] == "Reply"
    
    def test_error_system_not_persisted(self):
        """测试 ERROR_SYSTEM 不入库 - 关键策略！"""
        result = MessagePersistencePolicy.apply_policy(
            category=MessageCategory.ERROR_SYSTEM,
            content="401 Auth Failed"
        )
        assert result["should_persist"] is False
        assert result["content"] is None
    
    def test_error_business_is_persisted(self):
        """测试 ERROR_BUSINESS 入库供学习 - 关键策略！"""
        result = MessagePersistencePolicy.apply_policy(
            category=MessageCategory.ERROR_BUSINESS,
            content="Worker execution failed"
        )
        assert result["should_persist"] is True
        assert result["content"] == "Worker execution failed"
    
    def test_internal_reasoning_thinking_field(self):
        """测试 INTERNAL_REASONING 存入 thinking 字段，content 为空字符串"""
        result = MessagePersistencePolicy.apply_policy(
            category=MessageCategory.INTERNAL_REASONING,
            content="<think>思考过程</think>"
        )
        assert result["should_persist"] is True
        assert result["thinking"] == "<think>思考过程</think>"
        assert result["content"] == ""  # 实际代码设置为空字符串
    
    def test_internal_tool_call_not_persisted(self):
        """测试 INTERNAL_TOOL_CALL 不入库"""
        result = MessagePersistencePolicy.apply_policy(
            category=MessageCategory.INTERNAL_TOOL_CALL,
            content="Hidden tool output"
        )
        assert result["should_persist"] is False


class TestMessageStreamPolicy:
    """测试消息流式推送策略"""
    
    def test_user_message_streaming(self):
        """测试 USER 消息推送"""
        result = MessageStreamPolicy.apply_policy(
            category=MessageCategory.USER,
            content="Hello"
        )
        assert result["should_stream"] is True
        assert result["frontend_type"] == "human"
    
    def test_assistant_response_streaming(self):
        """测试 ASSISTANT_RESPONSE 推送"""
        result = MessageStreamPolicy.apply_policy(
            category=MessageCategory.ASSISTANT_RESPONSE,
            content="Reply"
        )
        assert result["should_stream"] is True
        assert result["frontend_type"] == "ai"
    
    def test_error_system_not_streamed(self):
        """测试 ERROR_SYSTEM 不流式推送 - 关键策略！"""
        result = MessageStreamPolicy.apply_policy(
            category=MessageCategory.ERROR_SYSTEM,
            content="Error"
        )
        assert result["should_stream"] is False
    
    def test_error_business_not_streamed(self):
        """测试 ERROR_BUSINESS 不流式推送 - 关键策略！"""
        result = MessageStreamPolicy.apply_policy(
            category=MessageCategory.ERROR_BUSINESS,
            content="Error"
        )
        assert result["should_stream"] is False
    
    def test_internal_reasoning_streaming(self):
        """测试 INTERNAL_REASONING 推送为 thought 类型（实际代码使用 thought）"""
        result = MessageStreamPolicy.apply_policy(
            category=MessageCategory.INTERNAL_REASONING,
            content="Thinking..."
        )
        assert result["should_stream"] is True
        assert result["frontend_type"] == "thought"  # 实际代码使用 thought
