"""SDK condenser 配置单测：整合教训回归——legacy ContextTrimmer 删除后压缩
职责必须由 SDK condenser 承担，Agent spec 漏配会导致长对话撞 context window。
"""

from __future__ import annotations

from openhands.sdk import LLM

from app.core.config import settings
from app.core.engine.sdk_adapter.session_bridge import _build_condenser

TEST_LLM = LLM(model="openai/mock-llm", api_key="mock", base_url="http://127.0.0.1:9")


class TestBuildCondenser:
    def test_default_settings_build_summary_condenser(self, monkeypatch):
        monkeypatch.setattr(settings, "SDK_CONDENSER_MAX_SIZE", 240)
        monkeypatch.setattr(settings, "SDK_CONDENSER_KEEP_FIRST", 2)
        condenser = _build_condenser(llm=TEST_LLM)
        assert condenser is not None
        assert condenser.max_size == 240
        assert condenser.keep_first == 2

    def test_disabled_when_max_size_zero(self, monkeypatch):
        monkeypatch.setattr(settings, "SDK_CONDENSER_MAX_SIZE", 0)
        assert _build_condenser(llm=TEST_LLM) is None

    def test_max_input_tokens_from_settings(self, monkeypatch):
        """create_sdk_llm 的 TOKENS 护栏：settings 值透传到 LLM.max_input_tokens。"""
        monkeypatch.setattr(settings, "SDK_LLM_MAX_INPUT_TOKENS", 64000)
        import asyncio

        from app.core.engine.sdk_adapter.llm import create_sdk_llm

        class _Ctx:
            token = "t"
            active_model = "test-model"

        async def _run():
            return await create_sdk_llm(_Ctx(), {"configurable": {}})

        llm = asyncio.run(_run())
        assert llm.max_input_tokens == 64000

    def test_keep_first_clamped_below_max_size_half(self, monkeypatch):
        """SDK 校验 keep_first < max_size // 2；过大的 keep_first 必须被钳制。"""
        monkeypatch.setattr(settings, "SDK_CONDENSER_MAX_SIZE", 10)
        monkeypatch.setattr(settings, "SDK_CONDENSER_KEEP_FIRST", 8)
        condenser = _build_condenser(llm=TEST_LLM)
        assert condenser is not None
        # SDK 要求 max_size//2 - keep_first - 1 > 0（压缩后尾部保留空间）
        assert 10 // 2 - condenser.keep_first - 1 > 0
