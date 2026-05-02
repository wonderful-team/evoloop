"""
测试 MessageHandler
"""
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.core.engine.message.category import MessageCategory
from app.core.engine.message.classifier import MessageClassifier
from app.core.engine.message.persistence import MessagePersistencePolicy

from app.core.engine.message.stream import MessageStreamPolicy


def test_persist_policy_for_internal_messages():
    """测试内部消息的持久化策略"""
    # 内部消息不应该持久化
    assert MessagePersistencePolicy.should_persist(MessageCategory.INTERNAL_LLM_JSON) is False
    assert MessagePersistencePolicy.should_persist(MessageCategory.INTERNAL_TOOL_CALL) is False
    assert MessagePersistencePolicy.should_persist(MessageCategory.INTERNAL_SYSTEM) is False
    
    # 用户可见消息应该持久化
    assert MessagePersistencePolicy.should_persist(MessageCategory.USER) is True
    assert MessagePersistencePolicy.should_persist(MessageCategory.ASSISTANT_RESPONSE) is True
    assert MessagePersistencePolicy.should_persist(MessageCategory.TOOL_OUTPUT) is True
    
    print("✅ test_persist_policy_for_internal_messages passed")


def test_stream_policy_for_internal_messages():
    """测试内部消息的推送策略"""
    # 内部消息不应该推送
    assert MessageStreamPolicy.should_stream(MessageCategory.INTERNAL_LLM_JSON) is False
    assert MessageStreamPolicy.should_stream(MessageCategory.INTERNAL_TOOL_CALL) is False
    assert MessageStreamPolicy.should_stream(MessageCategory.INTERNAL_SYSTEM) is False
    
    # 用户可见消息应该推送
    assert MessageStreamPolicy.should_stream(MessageCategory.ASSISTANT_RESPONSE) is True
    assert MessageStreamPolicy.should_stream(MessageCategory.TOOL_OUTPUT) is True
    
    print("✅ test_stream_policy_for_internal_messages passed")


def test_apply_policy_internal_llm_json():
    """测试内部 LLM JSON 响应的策略应用"""
    category = MessageCategory.INTERNAL_LLM_JSON
    content = '{"selected_indices": [1, 2], "reasoning": "test"}'
    
    result = MessagePersistencePolicy.apply_policy(category, content)
    
    assert result["should_persist"] is False
    assert result["content"] is None
    assert result["thinking"] is None
    assert result["category"] == "internal_llm_json"
    
    print("✅ test_apply_policy_internal_llm_json passed")


def test_apply_policy_internal_reasoning():
    """测试思考过程的策略应用"""
    category = MessageCategory.INTERNAL_REASONING
    content = "deep analysis reasoning"

    result = MessagePersistencePolicy.apply_policy(category, content)

    assert result["should_persist"] is True
    assert result["content"] == ""  # 思考过程 content 为空
    assert result["thinking"] == content  # 存入 thinking 字段（字符串）
    assert result["category"] == "internal_reasoning"

    print("✅ test_apply_policy_internal_reasoning passed")


def test_apply_policy_assistant_response():
    """测试正常 AI 回复的策略应用"""
    category = MessageCategory.ASSISTANT_RESPONSE
    content = "我来帮您处理这个任务"
    
    result = MessagePersistencePolicy.apply_policy(category, content)
    
    assert result["should_persist"] is True
    assert result["content"] == content
    assert result["thinking"] is None
    assert result["category"] == "assistant_response"
    
    print("✅ test_apply_policy_assistant_response passed")


def test_end_to_end_classification_and_policy():
    """测试端到端的分类和策略应用"""
    
    # 场景 1: Memory selection JSON
    content = '{"selected_indices": [1, 3], "reasoning": "Good match"}'
    category = MessageClassifier.classify_ai_message(content=content)
    
    assert category == MessageCategory.INTERNAL_LLM_JSON
    assert category.should_persist_to_db is False
    assert category.should_stream_to_frontend is False
    
    # 场景 2: 正常 AI 回复
    content = "我来帮您处理"
    category = MessageClassifier.classify_ai_message(content=content)
    
    assert category == MessageCategory.ASSISTANT_RESPONSE
    assert category.should_persist_to_db is True
    assert category.should_stream_to_frontend is True
    
    # 场景 3: 原生 reasoning_content（纯推理，无正文）
    category = MessageClassifier.classify_ai_message(
        content="", metadata={"reasoning_content": "分析中..."}
    )

    assert category == MessageCategory.INTERNAL_REASONING
    assert category.should_persist_to_db is True
    assert category.should_stream_to_frontend is True
    assert category.storage_field == "thinking"

    # 场景 4: 原生 reasoning_content + 正文 → 应为 ASSISTANT_RESPONSE，thinking 由 PersistencePolicy 处理
    content = "最终结果"
    category = MessageClassifier.classify_ai_message(
        content=content, metadata={"reasoning_content": "分析中..."}
    )

    assert category == MessageCategory.ASSISTANT_RESPONSE
    assert category.should_persist_to_db is True
    assert category.should_stream_to_frontend is True
    
    # 验证 PersistencePolicy 正确将 reasoning 存入 thinking 字段
    result = MessagePersistencePolicy.apply_policy(category, content, thinking="分析中...")
    assert result["thinking"] == "分析中..."
    assert result["content"] == content
    
    print("✅ test_end_to_end_classification_and_policy passed")


if __name__ == "__main__":
    test_persist_policy_for_internal_messages()
    test_stream_policy_for_internal_messages()
    test_apply_policy_internal_llm_json()
    test_apply_policy_internal_reasoning()
    test_apply_policy_assistant_response()
    test_end_to_end_classification_and_policy()
    
    print("\n✅ All handler tests passed!")
