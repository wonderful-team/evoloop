"""
测试 MessageClassifier
"""
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from app.core.messaging.category import MessageCategory
from app.core.messaging.classifier import MessageClassifier


def test_classify_internal_json():
    """测试内部 JSON 响应分类"""
    # Memory selection JSON
    content = '{"selected_indices": [1, 3], "reasoning": "Good match"}'
    cat = MessageClassifier.classify_ai_message(content=content)
    assert cat == MessageCategory.INTERNAL_LLM_JSON, f"Expected INTERNAL_LLM_JSON, got {cat}"
    
    # Task decomposition JSON
    content = '{"subtasks": [{"id": 1, "task": "test"}]}'
    cat = MessageClassifier.classify_ai_message(content=content)
    assert cat == MessageCategory.INTERNAL_LLM_JSON, f"Expected INTERNAL_LLM_JSON, got {cat}"
    
    print("✅ test_classify_internal_json passed")


def test_classify_reasoning():
    """测试思考内容分类"""
    content = "<think>我需要分析这个问题...</think>\n最终回复"
    cat = MessageClassifier.classify_ai_message(content=content)
    assert cat == MessageCategory.INTERNAL_REASONING, f"Expected INTERNAL_REASONING, got {cat}"
    
    content = "<audit>任务已完成</audit>"
    cat = MessageClassifier.classify_ai_message(content=content)
    assert cat == MessageCategory.INTERNAL_REASONING, f"Expected INTERNAL_REASONING, got {cat}"
    
    print("✅ test_classify_reasoning passed")


def test_classify_system_event():
    """测试系统事件分类"""
    content = "✅ SESSION COMPLETE"
    cat = MessageClassifier.classify_ai_message(content=content)
    assert cat == MessageCategory.INTERNAL_SYSTEM, f"Expected INTERNAL_SYSTEM, got {cat}"
    
    print("✅ test_classify_system_event passed")


def test_classify_assistant_response():
    """测试正常 AI 回复分类"""
    content = "我来帮您处理这个任务"
    cat = MessageClassifier.classify_ai_message(content=content)
    assert cat == MessageCategory.ASSISTANT_RESPONSE, f"Expected ASSISTANT_RESPONSE, got {cat}"
    
    content = "这是一个正常的回复，没有特殊标记"
    cat = MessageClassifier.classify_ai_message(content=content)
    assert cat == MessageCategory.ASSISTANT_RESPONSE, f"Expected ASSISTANT_RESPONSE, got {cat}"
    
    print("✅ test_classify_assistant_response passed")


def test_classify_with_metadata():
    """测试带有元数据的分类"""
    # 带有 internal_llm 标记的消息
    content = "some content"
    metadata = {"source": "internal_llm", "purpose": "memory_selection"}
    cat = MessageClassifier.classify_ai_message(content=content, metadata=metadata)
    assert cat == MessageCategory.INTERNAL_LLM_JSON, f"Expected INTERNAL_LLM_JSON, got {cat}"
    
    print("✅ test_classify_with_metadata passed")


def test_classify_normal_json():
    """测试普通 JSON（不是内部响应）"""
    # 普通的 JSON 回复给用户
    content = '{"result": "success", "data": [1, 2, 3]}'
    cat = MessageClassifier.classify_ai_message(content=content)
    # 不包含内部特征键，应该被视为正常回复
    assert cat == MessageCategory.ASSISTANT_RESPONSE, f"Expected ASSISTANT_RESPONSE, got {cat}"
    
    print("✅ test_classify_normal_json passed")


def test_is_internal_json_response():
    """测试内部 JSON 识别"""
    # 包含内部特征键
    assert MessageClassifier._is_internal_json_response('{"selected_indices": [1]}') is True
    assert MessageClassifier._is_internal_json_response('{"match_found": true}') is True
    assert MessageClassifier._is_internal_json_response('{"subtasks": []}') is True
    
    # 不包含内部特征键
    assert MessageClassifier._is_internal_json_response('{"result": "ok"}') is False
    assert MessageClassifier._is_internal_json_response('{"data": [1,2,3]}') is False
    
    # 非 JSON
    assert MessageClassifier._is_internal_json_response("普通文本") is False
    assert MessageClassifier._is_internal_json_response("") is False
    
    print("✅ test_is_internal_json_response passed")


def test_has_thinking_tags():
    """测试思考标签识别"""
    assert MessageClassifier._has_thinking_tags("<think>思考内容</think>") is True
    assert MessageClassifier._has_thinking_tags("<audit>审计内容</audit>") is True
    assert MessageClassifier._has_thinking_tags("<THINK>大写</THINK>") is True
    
    assert MessageClassifier._has_thinking_tags("普通文本") is False
    assert MessageClassifier._has_thinking_tags("") is False
    assert MessageClassifier._has_thinking_tags("没有标签") is False
    
    print("✅ test_has_thinking_tags passed")


def test_is_system_event():
    """测试系统事件识别"""
    assert MessageClassifier._is_system_event("✅ SESSION COMPLETE") is True
    assert MessageClassifier._is_system_event("❌ SESSION COMPLETE") is True
    assert MessageClassifier._is_system_event("SESSION COMPLETE") is True
    
    assert MessageClassifier._is_system_event("普通文本") is False
    assert MessageClassifier._is_system_event("") is False
    
    print("✅ test_is_system_event passed")


if __name__ == "__main__":
    test_classify_internal_json()
    test_classify_reasoning()
    test_classify_system_event()
    test_classify_assistant_response()
    test_classify_with_metadata()
    test_classify_normal_json()
    test_is_internal_json_response()
    test_has_thinking_tags()
    test_is_system_event()
    
    print("\n✅ All classifier tests passed!")
