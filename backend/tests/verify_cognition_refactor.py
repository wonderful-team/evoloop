
import asyncio
import unittest
from unittest.mock import patch

from app.constants import DEFAULT_MAX_CONTEXT_TOKENS
from app.core.engine.context_trimmer import ContextTrimmer, TrimResult, TrimTrigger
from app.core.engine.inference_engine import InferenceEngine
from app.core.engine.message.native_classes import (
    HumanMessage,
    SystemMessage,
)
from app.infrastructure.llm.platform_service import llm_platform_service
from app.infrastructure.schemas import PlatformModel


class TestCognitionRefactor(unittest.TestCase):
    def setUp(self):
        # Reset cache to ensure fresh tests
        llm_platform_service._models_cache = {}

    def test_dynamic_profile_fallback(self):
        """测试 128k 默认兜底逻辑"""
        # 1. 测试一个完全不存在的模型
        profile = llm_platform_service.get_profile("non-existent-model")
        print(f"Fallback Context Window: {profile.context_window}")
        self.assertEqual(profile.context_window, DEFAULT_MAX_CONTEXT_TOKENS)
        self.assertEqual(profile.max_context_tokens, DEFAULT_MAX_CONTEXT_TOKENS)

        # 2. 测试模糊匹配 (Vision 检测)
        gpt_profile = llm_platform_service.get_profile("gpt-4o-custom")
        # 由于我们现在改成了严格读取配置，如果没配配置，supports_vision 应该是 False
        # （除非在 Phase 1 查到了真正的平台模型）
        print(f"GPT-4o Custom Vision: {gpt_profile.supports_vision}")

    def test_zero_token_safety(self):
        """测试数据库返回 0 容量时的安全性"""
        # Mock get_model_by_id 返回一个容量为 0 的损坏记录
        mock_model = PlatformModel(
            model_id="broken-model",
            display_name="Broken",
            provider_name="openai",
            context_window=0  # 模拟坏数据
        )

        with patch.object(llm_platform_service, 'get_model_by_id', return_value=mock_model):
            profile = llm_platform_service.get_profile("broken-model")
            # 验证 get_profile 本身保留原值，但逻辑层会处理
            self.assertEqual(profile.context_window, 0)

            # 验证 ContextMonitor 是否能救场
            from app.core.engine.context_monitor import ContextMonitor
            stats = ContextMonitor.calculate([HumanMessage(content="hello")], model="broken-model")
            print(f"Safety Max Tokens: {stats.max_tokens}")
            self.assertEqual(stats.max_tokens, DEFAULT_MAX_CONTEXT_TOKENS)

    def test_dashboard_injection_in_engine(self):
        """测试 InferenceEngine 内部的实时仪表盘注入"""
        engine = InferenceEngine()

        # 构造一条带内容的人类消息
        messages = [
            SystemMessage(content="system"),
            HumanMessage(content="What is the weather?")
        ]

        # 模拟 Trimmer 返回结果
        mock_trim_result = TrimResult(
            messages=messages,
            trigger=TrimTrigger.NONE,
            before_tokens=1000,
            after_tokens=1000,
            before_count=2,
            after_count=2,
            removed_count=0
        )

        with patch.object(ContextTrimmer, 'trim', return_value=mock_trim_result):
            # 运行 _prepare_turn_context
            loop_messages, info = asyncio.run(engine._prepare_turn_context(
                loop_messages=messages,
                model="gpt-4o",
                name="Worker",
                thread_id="test",
                run_id="test",
                config={}
            ))

            # 验证最后一条 HumanMessage 的 content 是否被追加了 [Context Monitor]
            last_msg = loop_messages[-1]
            print(f"Injected Message Content:\n{last_msg.content}")

            self.assertIn("[Context Monitor]", last_msg.content)
            self.assertIn("Usage:", last_msg.content)
            # 验证是否包含 128k (或常量值)
            self.assertIn(f"{DEFAULT_MAX_CONTEXT_TOKENS:,}", last_msg.content)

if __name__ == "__main__":
    unittest.main()
