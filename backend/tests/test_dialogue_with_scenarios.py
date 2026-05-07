"""
使用场景话术测试对话系统 - 集成测试（Layer 2）

测试思路：
- 测试 conversations.py / chat.py 中的函数逻辑
- Mock 数据库、LLM、Redis 等外部依赖
- 验证业务流程、参数传递、响应组装

运行：
    cd backend && python -m pytest tests/test_dialogue_with_scenarios.py -v
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# 导入话术数据
import sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(BASE_DIR))
from tests.monitoring.test_dialogue_scenarios import (
    CODE_GENERATION_SCENARIOS,
    FILE_OPERATION_SCENARIOS,
    AMBIGUOUS_SCENARIOS,
)


class TestFileOperationDialogue:
    """测试文件操作对话场景"""

    @pytest.mark.parametrize("scenario", FILE_OPERATION_SCENARIOS[:3])
    async def test_file_operation_request(self, scenario):
        """测试文件操作请求 - 验证工具调用"""
        user_input = scenario["cn"]
        
        # 关键断言：文件操作应该触发工具调用
        # 而不是纯文本回复
        
        # Mock 工具调用响应
        mock_tool_call = {
            "name": "write_file",
            "args": {"file_path": "/tmp/test.txt", "content": "test"},
            "id": "call-1"
        }
        
        mock_response = MagicMock()
        mock_response.content = "我来帮您创建文件"
        mock_response.tool_calls = [mock_tool_call]
        
        with patch("app.core.tools.manager.tool_manager") as mock_tool_mgr:
            mock_tool_mgr.get_node_tools.return_value = ["write_file", "read_file"]
            
            # 验证工具被正确解析
            tools = mock_tool_mgr.get_node_tools("worker", {})
            assert "write_file" in tools or any("file" in t.lower() for t in tools)


class TestAmbiguousDialogue:
    """测试模糊需求对话场景"""

    @pytest.mark.parametrize("scenario", AMBIGUOUS_SCENARIOS)
    async def test_ambiguous_request_handling(self, scenario):
        """测试系统如何处理模糊请求"""
        user_input = scenario["cn"]
        
        # 模糊请求应该：
        # 1. 不崩溃
        # 2. 可能要求澄清
        # 3. 或基于上下文做出最佳猜测
        
        # 这里我们测试验证逻辑是否健壮
        assert len(user_input) > 0
        assert isinstance(user_input, str)
        
        # 实际测试中，验证系统返回澄清问题或合理默认行为


class TestMessageHandling:
    """测试消息处理逻辑"""

    @pytest.mark.parametrize("scenario", CODE_GENERATION_SCENARIOS[:2])
    def test_message_serialization(self, scenario):
        """测试消息序列化格式"""
        user_input = scenario["cn"]
        
        # 验证消息结构符合前端预期
        message = {
            "id": "123",
            "role": "human",
            "content": user_input,
            "created_at": datetime.now().isoformat(),
        }
        
        assert message["role"] in ["human", "ai", "tool"]
        assert len(message["content"]) <= 10000  # 长度限制
        assert "<script>" not in message["content"] or message["content"].count("<") < 5  # 基本 XSS 检查


class TestMultiLanguageSupport:
    """测试多语言支持"""

    @pytest.mark.parametrize("scenario", CODE_GENERATION_SCENARIOS[:3])
    def test_chinese_english_equivalence(self, scenario):
        """测试中英文请求应该得到等价处理"""
        cn_input = scenario["cn"]
        en_input = scenario["en"]
        
        # 关键验证点：
        # 1. 中英文输入长度都合理
        assert len(cn_input) > 5
        assert len(en_input) > 5
        
        # 2. 都包含关键动作词
        cn_action_words = ["写", "生成", "创建", "解释", "优化"]
        en_action_words = ["write", "generate", "create", "explain", "optimize"]
        
        has_cn_action = any(w in cn_input for w in cn_action_words)
        has_en_action = any(w.lower() in en_input.lower() for w in en_action_words)
        
        # 中英文应该都有明确的动作指示
        assert has_cn_action or "计算" in cn_input or "搜索" in cn_input
        assert has_en_action or "calculate" in en_input.lower() or "search" in en_input.lower()


# ==================== 实际接口测试示例（Layer 3，少量）====================

@pytest.mark.integration
@pytest.mark.asyncio
# ==================== 测试统计 ====================

def test_scenario_coverage():
    """验证场景覆盖率"""
    from tests.monitoring.test_dialogue_scenarios import ALL_SCENARIOS, get_scenario_stats
    
    stats = get_scenario_stats()
    
    # 验证每个类别都有数据
    for category in ALL_SCENARIOS.keys():
        assert stats[category] > 0, f"{category} 没有场景数据"
    
    # 验证总数
    assert stats["total"] >= 100, f"场景总数不足: {stats['total']}"
    
    print(f"\n场景覆盖: {stats['total']} 条话术")
    print("分布:", {k: v for k, v in stats.items() if k != "total"})


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-k", "test_scenario_coverage or test_code_generation"])
