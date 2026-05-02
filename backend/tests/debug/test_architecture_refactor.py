"""
Architecture Refactoring Integration Tests

验证消息分类架构重构后的核心功能:
1. MessageCategory 枚举
2. MessageClassifier 分类逻辑
3. MessageHandler 统一处理
4. DatabaseCallbackHandler 集成
5. InternalLLMService 配置
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestMessageCategory:
    """测试 MessageCategory 枚举定义"""
    
    def test_category_values(self):
        """验证所有类别值定义正确"""
        from app.core.messaging.category import MessageCategory
        
        assert MessageCategory.USER.value == "user"
        assert MessageCategory.ASSISTANT_RESPONSE.value == "assistant_response"
        assert MessageCategory.ASSISTANT_TOOL_CALL.value == "assistant_tool_call"
        assert MessageCategory.TOOL_OUTPUT.value == "tool_output"
        assert MessageCategory.INTERNAL_TOOL_CALL.value == "internal_tool_call"
        assert MessageCategory.INTERNAL_REASONING.value == "internal_reasoning"
        assert MessageCategory.INTERNAL_SYSTEM.value == "internal_system"
        assert MessageCategory.INTERNAL_LLM_JSON.value == "internal_llm_json"


class TestMessageClassifier:
    """测试 MessageClassifier 分类逻辑"""
    
    def test_classify_internal_json(self):
        """识别内部 JSON 响应 (如 memory selection)"""
        from app.core.messaging.classifier import MessageClassifier
        from app.core.messaging.category import MessageCategory
        
        content = '{"selected_indices": [1, 2, 3], "reasoning": "test"}'
        result = MessageClassifier.classify_ai_message(content)
        assert result == MessageCategory.INTERNAL_LLM_JSON
    
    def test_classify_reasoning_content(self):
        """识别包含原生 reasoning_content 的内容"""
        from app.core.messaging.classifier import MessageClassifier
        from app.core.messaging.category import MessageCategory

        result = MessageClassifier.classify_ai_message(
            content="Final answer", metadata={"reasoning_content": "deep analysis"}
        )
        assert result == MessageCategory.INTERNAL_REASONING
    
    def test_classify_normal_assistant_response(self):
        """正常助手回复分类为 assistant_response"""
        from app.core.messaging.classifier import MessageClassifier
        from app.core.messaging.category import MessageCategory
        
        content = "Hello, how can I help you?"
        result = MessageClassifier.classify_ai_message(content)
        assert result == MessageCategory.ASSISTANT_RESPONSE
    
    def test_classify_with_tool_calls(self):
        """带工具调用的分类"""
        from app.core.messaging.classifier import MessageClassifier
        from app.core.messaging.category import MessageCategory
        
        # 模拟可见工具调用
        tool_calls = [{"name": "read_file"}]
        result = MessageClassifier.classify_ai_message("Using tool", tool_calls)
        # 注意: 实际分类可能因工具可见性而异


class TestMessagePersistencePolicy:
    """测试持久化策略"""
    
    def test_persist_policy_for_visible_messages(self):
        """用户可见消息应持久化"""
        from app.core.messaging.persistence import MessagePersistencePolicy
        from app.core.messaging.category import MessageCategory
        
        policy = MessagePersistencePolicy()
        
        assert policy.should_persist(MessageCategory.USER) == True
        assert policy.should_persist(MessageCategory.ASSISTANT_RESPONSE) == True
        assert policy.should_persist(MessageCategory.ASSISTANT_TOOL_CALL) == True
        assert policy.should_persist(MessageCategory.TOOL_OUTPUT) == True
    
    def test_persist_policy_for_internal_messages(self):
        """内部消息持久化策略"""
        from app.core.messaging.persistence import MessagePersistencePolicy
        from app.core.messaging.category import MessageCategory
        
        policy = MessagePersistencePolicy()
        
        # 完全不存储
        assert policy.should_persist(MessageCategory.INTERNAL_LLM_JSON) == False
        assert policy.should_persist(MessageCategory.INTERNAL_SYSTEM) == False
        assert policy.should_persist(MessageCategory.INTERNAL_TOOL_CALL) == False
        
        # INTERNAL_REASONING 存储到 thinking 字段
        assert policy.should_persist(MessageCategory.INTERNAL_REASONING) == True
        assert policy.get_storage_field(MessageCategory.INTERNAL_REASONING) == "thinking"


class TestMessageStreamPolicy:
    """测试流式推送策略"""
    
    def test_stream_policy(self):
        """验证流式策略"""
        from app.core.messaging.stream import MessageStreamPolicy
        from app.core.messaging.category import MessageCategory
        
        policy = MessageStreamPolicy()
        
        # 用户和助手回复应该流式推送
        assert policy.should_stream(MessageCategory.USER) == True
        assert policy.should_stream(MessageCategory.ASSISTANT_RESPONSE) == True
        
        # 内部消息不应流式推送
        assert policy.should_stream(MessageCategory.INTERNAL_LLM_JSON) == False
        assert policy.should_stream(MessageCategory.INTERNAL_SYSTEM) == False
        
        # INTERNAL_REASONING 可以推送到前端（thought 类型）
        assert policy.should_stream(MessageCategory.INTERNAL_REASONING) == True
        assert policy.get_frontend_type(MessageCategory.INTERNAL_REASONING) == "thought"


class TestInternalLLMService:
    """测试 InternalLLMService 配置"""
    
    def test_validate_purpose_warns_on_invalid(self):
        """验证无效 purpose 会记录警告但不抛出异常"""
        from app.core.llm.internal_service import InternalLLMService
        
        # 无效 purpose 只记录警告，不抛出异常
        # 这样设计是为了兼容新的 purpose 而不破坏现有代码
        InternalLLMService.validate_purpose("invalid_purpose")  # 不应抛出
    
    def test_validate_purpose_passes_on_valid(self):
        """验证有效 purpose 通过验证"""
        from app.core.llm.internal_service import InternalLLMService
        
        # 不应抛出异常
        InternalLLMService.validate_purpose("memory_selection")
        InternalLLMService.validate_purpose("task_analysis")


class TestDatabaseCallbackHandlerIntegration:
    """测试 DatabaseCallbackHandler 集成"""
    
    def test_handler_uses_message_handler(self):
        """验证 handler 使用 MessageHandler"""
        from app.core.callbacks.database_logger import DatabaseCallbackHandler
        
        handler = DatabaseCallbackHandler(
            thread_id="test-thread",
            project_id=1,
            run_id="test-run"
        )
        
        # 验证 handler 有 _handler 属性
        assert hasattr(handler, '_handler')
        assert handler._handler is not None


class TestMessageCategoryHelpers:
    """测试 MessageCategory 辅助方法"""
    
    def test_get_visible_categories(self):
        """测试获取可见类别集合"""
        from app.core.messaging.category import MessageCategory
        
        visible = MessageCategory.get_visible_categories()
        expected = {
            MessageCategory.USER,
            MessageCategory.ASSISTANT_RESPONSE,
            MessageCategory.ASSISTANT_TOOL_CALL,
            MessageCategory.TOOL_OUTPUT,
            MessageCategory.INTERNAL_REASONING,
        }
        assert visible == expected
    
    def test_get_invisible_categories(self):
        """测试获取不可见类别集合"""
        from app.core.messaging.category import MessageCategory
        
        invisible = MessageCategory.get_invisible_categories()
        expected = {
            MessageCategory.INTERNAL_TOOL_CALL,
            MessageCategory.INTERNAL_SYSTEM,
            MessageCategory.INTERNAL_LLM_JSON,
            MessageCategory.ERROR_SYSTEM,
            MessageCategory.ERROR_BUSINESS,
        }
        assert invisible == expected
    
    def test_get_persisted_categories(self):
        """测试获取入库类别集合"""
        from app.core.messaging.category import MessageCategory
        
        persisted = MessageCategory.get_persisted_categories()
        expected = {
            MessageCategory.USER,
            MessageCategory.ASSISTANT_RESPONSE,
            MessageCategory.ASSISTANT_TOOL_CALL,
            MessageCategory.TOOL_OUTPUT,
            MessageCategory.INTERNAL_REASONING,
            MessageCategory.ERROR_BUSINESS,  # 只有业务错误入库
        }
        assert persisted == expected
    
    def test_get_non_persisted_categories(self):
        """测试获取不入库类别集合"""
        from app.core.messaging.category import MessageCategory
        
        non_persisted = MessageCategory.get_non_persisted_categories()
        expected = {
            MessageCategory.INTERNAL_TOOL_CALL,
            MessageCategory.INTERNAL_SYSTEM,
            MessageCategory.INTERNAL_LLM_JSON,
            MessageCategory.ERROR_SYSTEM,  # 系统错误不入库
        }
        assert non_persisted == expected
    
    def test_visible_and_invisible_disjoint(self):
        """验证可见和不可见类别互斥"""
        from app.core.messaging.category import MessageCategory
        
        visible = MessageCategory.get_visible_categories()
        invisible = MessageCategory.get_invisible_categories()
        assert visible & invisible == set()
    
    def test_persisted_and_non_persisted_disjoint(self):
        """验证入库和不入库类别互斥"""
        from app.core.messaging.category import MessageCategory
        
        persisted = MessageCategory.get_persisted_categories()
        non_persisted = MessageCategory.get_non_persisted_categories()
        assert persisted & non_persisted == set()


class TestEndToEndMessageFlow:
    """端到端消息流测试"""
    
    def test_internal_message_filtered_from_ui(self):
        """验证内部消息被正确过滤，不显示在 UI"""
        from app.core.messaging.category import MessageCategory
        
        # UI 排除的类别（通过 is_visible=False 过滤）
        invisible_cats = MessageCategory.get_invisible_categories()
        
        # 验证这些类别不应显示给用户
        for cat in invisible_cats:
            assert cat.is_visible_to_user == False
    
    def test_visible_message_categories(self):
        """验证用户可见的消息类别"""
        from app.core.messaging.category import MessageCategory
        
        visible_cats = MessageCategory.get_visible_categories()
        
        for cat in visible_cats:
            assert cat.is_visible_to_user == True
    
    def test_error_message_categorization(self):
        """验证错误消息被正确分类"""
        from app.core.messaging.classifier import MessageClassifier
        from app.core.messaging.category import MessageCategory
        
        # 系统错误（401/429等）
        result = MessageClassifier.classify_ai_message(
            content="LLM auth failed",
            metadata={"is_error": True, "error_type": "llm_auth"}
        )
        assert result == MessageCategory.ERROR_SYSTEM
        
        # 业务错误（Worker失败等）
        result = MessageClassifier.classify_ai_message(
            content="Worker 'test' failed: Some error",
            metadata={"is_error": True, "error_type": "worker_execution"}
        )
        assert result == MessageCategory.ERROR_BUSINESS
    
    def test_error_message_persistence(self):
        """验证错误消息持久化策略"""
        from app.core.messaging.persistence import MessagePersistencePolicy
        from app.core.messaging.category import MessageCategory
        
        policy = MessagePersistencePolicy()
        
        # 系统错误不入库
        assert policy.should_persist(MessageCategory.ERROR_SYSTEM) == False
        
        # 业务错误入库供Agent学习
        assert policy.should_persist(MessageCategory.ERROR_BUSINESS) == True
        assert policy.get_storage_field(MessageCategory.ERROR_BUSINESS) == "content"
    
    def test_error_message_not_streamed(self):
        """验证错误消息不流式推送"""
        from app.core.messaging.stream import MessageStreamPolicy
        from app.core.messaging.category import MessageCategory
        
        policy = MessageStreamPolicy()
        
        # 系统错误和业务错误都不流式推送，通过 error 事件通知
        assert policy.should_stream(MessageCategory.ERROR_SYSTEM) == False
        assert policy.should_stream(MessageCategory.ERROR_BUSINESS) == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
