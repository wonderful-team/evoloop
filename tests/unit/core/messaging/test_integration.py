"""
端到端集成测试 - 验证完整消息处理流程
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.core.messaging.category import MessageCategory
from app.core.messaging.classifier import MessageClassifier
from app.core.messaging.handler import MessageHandler
from app.core.messaging.persistence import MessagePersistencePolicy
from app.core.messaging.stream import MessageStreamPolicy


class TestErrorClassificationIntegration:
    """
    集成测试：ERROR_SYSTEM vs ERROR_BUSINESS 分类
    
    验证真实场景下的错误分类逻辑：
    - 401/429/recursion_limit → ERROR_SYSTEM (不入库)
    - Worker/Aggregation 失败 → ERROR_BUSINESS (入库供学习)
    """
    
    def test_llm_401_error_flow(self):
        """测试 LLM 401 错误完整流程"""
        # 1. 分类
        category = MessageClassifier.classify_ai_message(
            content="Authentication failed: 401",
            metadata={"is_error": True, "error_type": "llm_auth", "status_code": 401}
        )
        assert category == MessageCategory.ERROR_SYSTEM
        
        # 2. 持久化策略
        persist = MessagePersistencePolicy.apply_policy(category, content="Auth failed")
        assert persist["should_persist"] is False  # 关键：不入库！
        
        # 3. 流式策略
        stream = MessageStreamPolicy.apply_policy(category, content="Auth failed")
        assert stream["should_stream"] is False  # 关键：不流式推送！
    
    def test_rate_limit_429_error_flow(self):
        """测试速率限制 429 错误完整流程"""
        category = MessageClassifier.classify_ai_message(
            content="Rate limit exceeded",
            metadata={"is_error": True, "error_type": "rate_limit", "retry_after": 60}
        )
        assert category == MessageCategory.ERROR_SYSTEM
        
        persist = MessagePersistencePolicy.apply_policy(category, content="Rate limited")
        assert persist["should_persist"] is False
    
    def test_worker_execution_error_flow(self):
        """测试 Worker 执行错误完整流程"""
        # 1. 分类
        category = MessageClassifier.classify_ai_message(
            content="Worker 'file_reader' failed: File not found",
            metadata={"is_error": True, "error_type": "worker_execution", "worker": "file_reader"}
        )
        assert category == MessageCategory.ERROR_BUSINESS
        
        # 2. 持久化策略
        persist = MessagePersistencePolicy.apply_policy(
            category, 
            content="Worker 'file_reader' failed: File not found"
        )
        assert persist["should_persist"] is True  # 关键：入库供学习！
        assert persist["content"] == "Worker 'file_reader' failed: File not found"
        
        # 3. 流式策略
        stream = MessageStreamPolicy.apply_policy(category, content="Worker failed")
        assert stream["should_stream"] is False  # 不流式推送（避免用户看到错误）
    
    def test_aggregation_error_flow(self):
        """测试聚合失败错误完整流程"""
        category = MessageClassifier.classify_ai_message(
            content="Failed to aggregate results from 3 workers",
            metadata={"is_error": True, "error_type": "aggregation_failed"}
        )
        assert category == MessageCategory.ERROR_BUSINESS
        
        persist = MessagePersistencePolicy.apply_policy(category, content="Aggregation failed")
        assert persist["should_persist"] is True  # 入库供学习
    
    def test_recursion_limit_error_flow(self):
        """测试递归限制错误完整流程"""
        category = MessageClassifier.classify_ai_message(
            content="Maximum recursion depth exceeded",
            metadata={"is_error": True, "error_type": "recursion_limit"}
        )
        assert category == MessageCategory.ERROR_SYSTEM
        
        persist = MessagePersistencePolicy.apply_policy(category, content="Recursion limit")
        assert persist["should_persist"] is False  # 不入库


class TestNormalMessageFlowIntegration:
    """正常消息流程集成测试"""
    
    def test_user_message_full_flow(self):
        """测试用户消息完整流程"""
        category = MessageClassifier.classify_user_message("Hello AI")
        assert category == MessageCategory.USER
        
        persist = MessagePersistencePolicy.apply_policy(category, content="Hello AI")
        assert persist["should_persist"] is True
        assert persist["content"] == "Hello AI"
        
        stream = MessageStreamPolicy.apply_policy(category, content="Hello AI")
        assert stream["should_stream"] is True
        assert stream["frontend_type"] == "human"
    
    def test_assistant_response_full_flow(self):
        """测试 AI 回复完整流程"""
        category = MessageClassifier.classify_ai_message("I can help you with that")
        assert category == MessageCategory.ASSISTANT_RESPONSE
        
        persist = MessagePersistencePolicy.apply_policy(category, content="I can help")
        assert persist["should_persist"] is True
        
        stream = MessageStreamPolicy.apply_policy(category, content="I can help")
        assert stream["should_stream"] is True
        assert stream["frontend_type"] == "ai"
    
    def test_thinking_message_full_flow(self):
        """测试思考过程完整流程"""
        category = MessageClassifier.classify_ai_message("<think>Let me analyze...</think>")
        assert category == MessageCategory.INTERNAL_REASONING
        
        persist = MessagePersistencePolicy.apply_policy(
            category, 
            content="<think>Let me analyze...</think>"
        )
        assert persist["should_persist"] is True
        assert persist["thinking"] == "<think>Let me analyze...</think>"
        
        stream = MessageStreamPolicy.apply_policy(category, content="Let me analyze...")
        assert stream["should_stream"] is True
        assert stream["frontend_type"] == "thought"
    
    def test_internal_json_not_persisted(self):
        """测试内部 JSON 不入库"""
        category = MessageClassifier.classify_ai_message(
            content='{"selected_indices": [1, 2]}'
        )
        assert category == MessageCategory.INTERNAL_LLM_JSON
        
        persist = MessagePersistencePolicy.apply_policy(category, content='{"selected_indices": [1]}')
        assert persist["should_persist"] is False


class TestMessageHandlerIntegration:
    """测试 MessageHandler 集成"""
    
    @pytest.mark.asyncio
    async def test_handler_processes_error_system(self):
        """测试 Handler 正确处理 ERROR_SYSTEM"""
        handler = MessageHandler(thread_id="test-thread")
        
        with patch.object(handler, '_persist_to_db', new_callable=AsyncMock) as mock_persist, \
             patch.object(handler, '_stream_to_frontend', new_callable=AsyncMock) as mock_stream:
            
            result = await handler.handle_ai_message(
                content="401 Auth Failed",
                metadata={"is_error": True, "error_type": "llm_auth"}
            )
            
            assert result["category"] == "error_system"
            assert result["persisted"] is False  # 不入库
            assert result["streamed"] is False   # 不推送
            mock_persist.assert_not_awaited()
            mock_stream.assert_not_awaited()
    
    @pytest.mark.asyncio
    async def test_handler_processes_error_business(self):
        """测试 Handler 正确处理 ERROR_BUSINESS"""
        handler = MessageHandler(thread_id="test-thread")
        
        with patch.object(handler, '_persist_to_db', new_callable=AsyncMock) as mock_persist, \
             patch.object(handler, '_stream_to_frontend', new_callable=AsyncMock) as mock_stream:
            
            result = await handler.handle_ai_message(
                content="Worker failed",
                metadata={"is_error": True, "error_type": "worker_execution"}
            )
            
            assert result["category"] == "error_business"
            assert result["persisted"] is True   # 入库！
            assert result["streamed"] is False   # 不推送
            mock_persist.assert_awaited_once()
            mock_stream.assert_not_awaited()
    
    @pytest.mark.asyncio
    async def test_handler_processes_normal_response(self):
        """测试 Handler 处理正常 AI 回复"""
        handler = MessageHandler(thread_id="test-thread")
        
        with patch.object(handler, '_persist_to_db', new_callable=AsyncMock) as mock_persist, \
             patch.object(handler, '_stream_to_frontend', new_callable=AsyncMock) as mock_stream:
            
            result = await handler.handle_ai_message(
                content="I can help you!"
            )
            
            assert result["category"] == "assistant_response"
            assert result["persisted"] is True   # 入库
            assert result["streamed"] is True    # 推送
            mock_persist.assert_awaited_once()
            mock_stream.assert_awaited_once()
