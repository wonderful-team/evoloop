"""
测试 MessageCategory 枚举的正确性
"""

import pytest
from app.core.messaging.category import MessageCategory


class TestMessageCategoryProperties:
    """测试消息分类属性"""
    
    def test_user_category_properties(self):
        """测试 USER 类别属性"""
        cat = MessageCategory.USER
        assert cat.is_visible_to_user is True
        assert cat.should_persist_to_db is True
        assert cat.should_stream_to_frontend is True
        assert cat.storage_field == "content"
    
    def test_assistant_response_properties(self):
        """测试 ASSISTANT_RESPONSE 类别属性"""
        cat = MessageCategory.ASSISTANT_RESPONSE
        assert cat.is_visible_to_user is True
        assert cat.should_persist_to_db is True
        assert cat.should_stream_to_frontend is True
        assert cat.storage_field == "content"
    
    def test_assistant_tool_call_properties(self):
        """测试 ASSISTANT_TOOL_CALL 类别属性"""
        cat = MessageCategory.ASSISTANT_TOOL_CALL
        assert cat.is_visible_to_user is True
        assert cat.should_persist_to_db is True
        assert cat.should_stream_to_frontend is True
        assert cat.storage_field == "content"
    
    def test_tool_output_properties(self):
        """测试 TOOL_OUTPUT 类别属性"""
        cat = MessageCategory.TOOL_OUTPUT
        assert cat.is_visible_to_user is True
        assert cat.should_persist_to_db is True
        assert cat.should_stream_to_frontend is True
        assert cat.storage_field == "content"
    
    def test_internal_reasoning_properties(self):
        """测试 INTERNAL_REASONING 类别属性 - 思考过程特殊处理"""
        cat = MessageCategory.INTERNAL_REASONING
        assert cat.is_visible_to_user is True  # 对用户可见（思考过程）
        assert cat.should_persist_to_db is True  # 入库
        assert cat.should_stream_to_frontend is True  # 流式推送
        assert cat.storage_field == "thinking"  # 存入 thinking 字段
    
    def test_internal_tool_call_properties(self):
        """测试 INTERNAL_TOOL_CALL 类别属性 - 完全内部"""
        cat = MessageCategory.INTERNAL_TOOL_CALL
        assert cat.is_visible_to_user is False
        assert cat.should_persist_to_db is False
        assert cat.should_stream_to_frontend is False
        assert cat.storage_field is None
    
    def test_internal_system_properties(self):
        """测试 INTERNAL_SYSTEM 类别属性"""
        cat = MessageCategory.INTERNAL_SYSTEM
        assert cat.is_visible_to_user is False
        assert cat.should_persist_to_db is False
        assert cat.should_stream_to_frontend is False
        assert cat.storage_field is None
    
    def test_internal_llm_json_properties(self):
        """测试 INTERNAL_LLM_JSON 类别属性"""
        cat = MessageCategory.INTERNAL_LLM_JSON
        assert cat.is_visible_to_user is False
        assert cat.should_persist_to_db is False
        assert cat.should_stream_to_frontend is False
        assert cat.storage_field is None
    
    def test_error_system_properties(self):
        """
        测试 ERROR_SYSTEM 类别属性 - 系统错误
        
        关键特性：
        - 不入库（无学习价值）
        - 不入消息列表（通过 error 事件通知）
        - 不流式推送
        """
        cat = MessageCategory.ERROR_SYSTEM
        assert cat.is_visible_to_user is False  # 不在消息列表显示
        assert cat.should_persist_to_db is False  # 不入库！
        assert cat.should_stream_to_frontend is False  # 不流式推送
        assert cat.storage_field is None
    
    def test_error_business_properties(self):
        """
        测试 ERROR_BUSINESS 类别属性 - 业务错误
        
        关键特性：
        - 入库（供 Agent 学习）
        - 不入消息列表（避免用户看到错误堆栈）
        - 不流式推送
        """
        cat = MessageCategory.ERROR_BUSINESS
        assert cat.is_visible_to_user is False  # 不在消息列表显示
        assert cat.should_persist_to_db is True  # 入库供学习！
        assert cat.should_stream_to_frontend is False  # 不流式推送
        assert cat.storage_field == "content"


class TestMessageCategoryClassMethods:
    """测试类方法"""
    
    def test_get_visible_categories(self):
        """测试获取可见类别"""
        visible = MessageCategory.get_visible_categories()
        expected = {
            MessageCategory.USER,
            MessageCategory.ASSISTANT_RESPONSE,
            MessageCategory.ASSISTANT_TOOL_CALL,
            MessageCategory.TOOL_OUTPUT,
            MessageCategory.INTERNAL_REASONING,
        }
        assert visible == expected
        # 确保错误类别不可见
        assert MessageCategory.ERROR_SYSTEM not in visible
        assert MessageCategory.ERROR_BUSINESS not in visible
    
    def test_get_invisible_categories(self):
        """测试获取不可见类别"""
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
        """测试获取入库类别"""
        persisted = MessageCategory.get_persisted_categories()
        expected = {
            MessageCategory.USER,
            MessageCategory.ASSISTANT_RESPONSE,
            MessageCategory.ASSISTANT_TOOL_CALL,
            MessageCategory.TOOL_OUTPUT,
            MessageCategory.INTERNAL_REASONING,
            MessageCategory.ERROR_BUSINESS,  # 业务错误入库
        }
        assert persisted == expected
        # 确保系统错误不入库
        assert MessageCategory.ERROR_SYSTEM not in persisted
    
    def test_get_non_persisted_categories(self):
        """测试获取不入库类别"""
        non_persisted = MessageCategory.get_non_persisted_categories()
        expected = {
            MessageCategory.INTERNAL_TOOL_CALL,
            MessageCategory.INTERNAL_SYSTEM,
            MessageCategory.INTERNAL_LLM_JSON,
            MessageCategory.ERROR_SYSTEM,  # 系统错误不入库
        }
        assert non_persisted == expected


class TestMessageCategoryEnum:
    """测试枚举基本功能"""
    
    def test_all_categories_defined(self):
        """测试所有 10 个类别都已定义"""
        expected = {
            "user",
            "assistant_response",
            "assistant_tool_call",
            "tool_output",
            "internal_tool_call",
            "internal_reasoning",
            "internal_system",
            "internal_llm_json",
            "error_system",
            "error_business",
        }
        actual = {cat.value for cat in MessageCategory}
        assert actual == expected
    
    def test_category_value_access(self):
        """测试通过值访问类别"""
        assert MessageCategory("user") == MessageCategory.USER
        assert MessageCategory("error_system") == MessageCategory.ERROR_SYSTEM
        assert MessageCategory("error_business") == MessageCategory.ERROR_BUSINESS
    
    def test_category_string_comparison(self):
        """测试字符串比较"""
        assert MessageCategory.USER == "user"
        assert MessageCategory.ERROR_SYSTEM == "error_system"
