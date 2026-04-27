"""
测试 MessageCategory 枚举
"""
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.core.engine.message.category import MessageCategory


def test_category_values():
    """测试分类值"""
    assert MessageCategory.USER.value == "user"
    assert MessageCategory.ASSISTANT_RESPONSE.value == "assistant_response"
    assert MessageCategory.INTERNAL_LLM_JSON.value == "internal_llm_json"


def test_is_visible_to_user():
    """测试用户可见性"""
    # 用户可见（显示在消息列表中）
    assert MessageCategory.USER.is_visible_to_user is True
    assert MessageCategory.ASSISTANT_RESPONSE.is_visible_to_user is True
    assert MessageCategory.ASSISTANT_TOOL_CALL.is_visible_to_user is True
    assert MessageCategory.TOOL_OUTPUT.is_visible_to_user is True
    assert MessageCategory.INTERNAL_REASONING.is_visible_to_user is True  # 思考过程对用户可见
    
    # 用户不可见（不显示在消息列表中）
    assert MessageCategory.INTERNAL_TOOL_CALL.is_visible_to_user is False
    assert MessageCategory.INTERNAL_SYSTEM.is_visible_to_user is False
    assert MessageCategory.INTERNAL_LLM_JSON.is_visible_to_user is False
    assert MessageCategory.ERROR_SYSTEM.is_visible_to_user is False  # 系统错误不入列表
    assert MessageCategory.ERROR_BUSINESS.is_visible_to_user is False  # 业务错误不入列表


def test_should_persist_to_db():
    """测试持久化规则"""
    # 应该持久化
    assert MessageCategory.USER.should_persist_to_db is True
    assert MessageCategory.ASSISTANT_RESPONSE.should_persist_to_db is True
    assert MessageCategory.ASSISTANT_TOOL_CALL.should_persist_to_db is True
    assert MessageCategory.TOOL_OUTPUT.should_persist_to_db is True
    assert MessageCategory.INTERNAL_REASONING.should_persist_to_db is True
    assert MessageCategory.ERROR_BUSINESS.should_persist_to_db is True  # 业务错误入库供Agent学习
    
    # 不应该持久化
    assert MessageCategory.INTERNAL_TOOL_CALL.should_persist_to_db is False
    assert MessageCategory.INTERNAL_SYSTEM.should_persist_to_db is False
    assert MessageCategory.INTERNAL_LLM_JSON.should_persist_to_db is False
    assert MessageCategory.ERROR_SYSTEM.should_persist_to_db is False  # 系统错误不入库


def test_storage_field():
    """测试存储字段映射"""
    assert MessageCategory.USER.storage_field == "content"
    assert MessageCategory.ASSISTANT_RESPONSE.storage_field == "content"
    assert MessageCategory.INTERNAL_REASONING.storage_field == "thinking"
    assert MessageCategory.INTERNAL_TOOL_CALL.storage_field is None
    assert MessageCategory.INTERNAL_LLM_JSON.storage_field is None


def test_should_stream_to_frontend():
    """测试推送规则"""
    # 应该推送
    assert MessageCategory.USER.should_stream_to_frontend is True
    assert MessageCategory.ASSISTANT_RESPONSE.should_stream_to_frontend is True
    assert MessageCategory.ASSISTANT_TOOL_CALL.should_stream_to_frontend is True
    assert MessageCategory.TOOL_OUTPUT.should_stream_to_frontend is True
    assert MessageCategory.INTERNAL_REASONING.should_stream_to_frontend is True
    
    # 错误消息通过 SSE 推送（前端显示错误卡片）
    assert MessageCategory.ERROR_SYSTEM.should_stream_to_frontend is True
    assert MessageCategory.ERROR_BUSINESS.should_stream_to_frontend is True
    assert MessageCategory.AUTH_EXPIRED.should_stream_to_frontend is True
    
    # 不应该推送
    assert MessageCategory.INTERNAL_TOOL_CALL.should_stream_to_frontend is False
    assert MessageCategory.INTERNAL_SYSTEM.should_stream_to_frontend is False
    assert MessageCategory.INTERNAL_LLM_JSON.should_stream_to_frontend is False


if __name__ == "__main__":
    test_category_values()
    print("✅ test_category_values passed")
    
    test_is_visible_to_user()
    print("✅ test_is_visible_to_user passed")
    
    test_should_persist_to_db()
    print("✅ test_should_persist_to_db passed")
    
    test_storage_field()
    print("✅ test_storage_field passed")
    
    test_should_stream_to_frontend()
    print("✅ test_should_stream_to_frontend passed")
    
    print("\n✅ All tests passed!")
