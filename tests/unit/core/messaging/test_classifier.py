"""
测试 MessageClassifier 分类逻辑
"""

import pytest
from unittest.mock import patch, MagicMock

from app.core.messaging.classifier import MessageClassifier
from app.core.messaging.category import MessageCategory


class TestClassifyUserMessage:
    """测试用户消息分类"""
    
    def test_user_message_classification(self):
        """测试用户消息始终分类为 USER"""
        result = MessageClassifier.classify_user_message("Hello")
        assert result == MessageCategory.USER
        
        result = MessageClassifier.classify_user_message("", metadata={})
        assert result == MessageCategory.USER
        
        result = MessageClassifier.classify_user_message("复杂内容\n多行")
        assert result == MessageCategory.USER


class TestClassifyAIErrorMessages:
    """测试 AI 错误消息分类 - ERROR_SYSTEM vs ERROR_BUSINESS"""
    
    def test_llm_auth_error_classification(self):
        """测试 LLM 401 认证错误分类为 ERROR_SYSTEM"""
        result = MessageClassifier.classify_ai_message(
            content="Authentication failed",
            metadata={"is_error": True, "error_type": "llm_auth"}
        )
        assert result == MessageCategory.ERROR_SYSTEM
    
    def test_rate_limit_error_classification(self):
        """测试速率限制错误分类为 ERROR_SYSTEM"""
        result = MessageClassifier.classify_ai_message(
            content="Rate limit exceeded",
            metadata={"is_error": True, "error_type": "rate_limit"}
        )
        assert result == MessageCategory.ERROR_SYSTEM
    
    def test_quota_exhausted_error_classification(self):
        """测试配额耗尽错误分类为 ERROR_SYSTEM"""
        result = MessageClassifier.classify_ai_message(
            content="Quota exhausted",
            metadata={"is_error": True, "error_type": "quota_exhausted"}
        )
        assert result == MessageCategory.ERROR_SYSTEM
    
    def test_recursion_limit_error_classification(self):
        """测试递归限制错误分类为 ERROR_SYSTEM"""
        result = MessageClassifier.classify_ai_message(
            content="Recursion limit reached",
            metadata={"is_error": True, "error_type": "recursion_limit"}
        )
        assert result == MessageCategory.ERROR_SYSTEM
    
    def test_worker_execution_error_classification(self):
        """测试 Worker 执行错误分类为 ERROR_BUSINESS"""
        result = MessageClassifier.classify_ai_message(
            content="Worker execution failed",
            metadata={"is_error": True, "error_type": "worker_execution"}
        )
        assert result == MessageCategory.ERROR_BUSINESS
    
    def test_aggregation_failed_error_classification(self):
        """测试聚合失败错误分类为 ERROR_BUSINESS"""
        result = MessageClassifier.classify_ai_message(
            content="Aggregation failed",
            metadata={"is_error": True, "error_type": "aggregation_failed"}
        )
        assert result == MessageCategory.ERROR_BUSINESS
    
    def test_unknown_error_defaults_to_business(self):
        """测试未知错误类型默认分类为 ERROR_BUSINESS"""
        result = MessageClassifier.classify_ai_message(
            content="Some random error",
            metadata={"is_error": True, "error_type": "unknown_error"}
        )
        assert result == MessageCategory.ERROR_BUSINESS
    
    def test_error_without_type_defaults_to_business(self):
        """测试错误无类型时默认分类为 ERROR_BUSINESS"""
        result = MessageClassifier.classify_ai_message(
            content="Error without type",
            metadata={"is_error": True}
        )
        assert result == MessageCategory.ERROR_BUSINESS


class TestClassifyAIReasoningMessages:
    """测试 AI 思考消息分类"""
    
    def test_think_tag_classification(self):
        """测试 <think> 标签分类为 INTERNAL_REASONING"""
        result = MessageClassifier.classify_ai_message(
            content="<think>这是思考过程</think>"
        )
        assert result == MessageCategory.INTERNAL_REASONING
    
    def test_audit_tag_classification(self):
        """测试 <audit> 标签分类为 INTERNAL_REASONING"""
        result = MessageClassifier.classify_ai_message(
            content="<audit>审计内容</audit>"
        )
        assert result == MessageCategory.INTERNAL_REASONING


class TestClassifyAIInternalJSON:
    """测试内部 JSON 响应分类"""
    
    def test_memory_selection_json_classification(self):
        """测试 memory selection JSON 自动识别"""
        result = MessageClassifier.classify_ai_message(
            content='{"selected_indices": [1, 2], "reasoning": "相关记忆"}'
        )
        assert result == MessageCategory.INTERNAL_LLM_JSON
    
    def test_normal_json_not_internal(self):
        """测试普通 JSON 不识别为内部响应"""
        result = MessageClassifier.classify_ai_message(
            content='{"message": "普通回复", "status": "ok"}'
        )
        assert result == MessageCategory.ASSISTANT_RESPONSE


class TestClassifyNormalAIResponse:
    """测试普通 AI 回复分类"""
    
    def test_simple_response_classification(self):
        """测试简单回复分类为 ASSISTANT_RESPONSE"""
        result = MessageClassifier.classify_ai_message(
            content="这是普通回复"
        )
        assert result == MessageCategory.ASSISTANT_RESPONSE
    
    def test_empty_content_classification(self):
        """测试空内容分类"""
        result = MessageClassifier.classify_ai_message(content="")
        assert result == MessageCategory.ASSISTANT_RESPONSE
