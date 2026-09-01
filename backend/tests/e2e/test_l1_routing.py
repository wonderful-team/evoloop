"""阶段30：L1 路由层（高层意图分类与委派）确定性测试。

对应链路 入口 → L0 → **L1** → Agent 中的 L1 层：
- ``compound_detector``：复合/多意图句检测（纯正则）
- ``action_classifier`` / ``domain_classifier``：L0 动作 / L1 域分类器
  （本测试只覆盖**模型无关的输入守卫契约**，模型推理精确性不在此断言）
- ``decision_builder``：L0 动作 → 通道无关 RouteDecision
- ``IntentResolver``：BERT 意图标签 → 上下文重定向 / 设备词覆盖 / 意图守卫 /
  复杂查询委派（数据来自 app/core/routing/data/ 的 YAML，无需 LLM/DB）

全部为进程内确定性测试，不依赖后端服务、不依赖 ONNX 模型与 LLM 配额。
"""

from __future__ import annotations

import pytest

from app.core.routing.compound_detector import is_compound_intent
from app.core.routing.decision_builder import build_decision
from app.core.routing.intent_resolution import IntentResolver
from app.core.routing.routing_data import RoutingLanguageStore

pytestmark = pytest.mark.e2e


class TestCompoundIntent:
    """L1 复合意图检测（纯正则，覆盖正反例与防误报）。"""

    def test_sequential_marker_with_action_is_compound(self) -> None:
        assert is_compound_intent("打开微信然后发消息") is True
        assert is_compound_intent("先打开微信再截图") is True
        assert is_compound_intent("搜索资料并且整理") is True
        assert is_compound_intent("打开浏览器之后搜索Python") is True

    def test_coord_marker_requires_two_actions(self) -> None:
        assert is_compound_intent("打开微信和搜索资料") is True
        assert is_compound_intent("发送文件及打开邮件") is True

    def test_give_marker_requires_two_actions(self) -> None:
        assert is_compound_intent("打开微信给张三发消息") is True
        # 经典防误报：单动作 + "给" 收件人不应判为复合意图
        assert is_compound_intent("发消息给张三") is False
        assert is_compound_intent("发邮件给老板") is False

    def test_single_action_is_not_compound(self) -> None:
        assert is_compound_intent("打开微信") is False
        assert is_compound_intent("计算一下") is False
        assert is_compound_intent("保存文件") is False
        assert is_compound_intent("") is False


class TestDecisionBuilder:
    """L1 决策构建：L0 动作 → 通道无关 RouteDecision。"""

    def test_macro_action_builds_macro_decision(self) -> None:
        decision = build_decision("macro:42", {"slot": "微信"}, 0.95, "voice")
        assert decision.status == "routed"
        assert decision.target_type == "macro"
        assert decision.target == {"type": "macro", "id": 42}
        assert decision.intent_hint.intent == "macro_task"
        assert decision.source == "voice"

    def test_local_action_builds_local_decision(self) -> None:
        decision = build_decision("open_app", {"app": "微信"}, 0.8, "web")
        assert decision.status == "routed"
        assert decision.target_type == "local"
        assert decision.target == {"type": "local", "action": "open_app"}
        assert decision.intent_hint.intent == "macro_task"


class TestClassifierGuards:
    """分类器模型无关的输入守卫（不加载 ONNX，仅验证拒绝路径）。"""

    def test_action_classifier_rejects_invalid_input(self) -> None:
        from app.core.routing.action_classifier import predict

        assert predict("") == (None, 0.0)
        assert predict("   ") == (None, 0.0)
        assert predict("。。。") == (None, 0.0)
        assert predict("!@#$%") == (None, 0.0)
        assert predict("12345") == (None, 0.0)

    def test_domain_classifier_rejects_empty(self) -> None:
        from app.core.routing.domain_classifier import predict

        assert predict("") == (None, 0.0)
        assert predict("   ") == (None, 0.0)


class TestDomainIntentHint:
    """L1 域分类标签 → IntentHint 映射（确定性）。"""

    def test_label_maps_to_domain_classified_hint(self) -> None:
        from app.core.routing.domain_classifier import to_intent_hint

        hint = to_intent_hint("coding", 0.92)
        assert hint.domain == "coding"
        assert hint.intent == "domain_classified"
        assert hint.confidence == 0.92
        assert hint.reason == "domain: coding"

    def test_empty_label_maps_to_ambiguous(self) -> None:
        from app.core.routing.domain_classifier import to_intent_hint

        hint = to_intent_hint("", 0.1)
        assert hint.domain == "ambiguous"
        assert hint.intent == "domain_classified"


class TestIntentResolver:
    """L1 意图解析：复杂查询委派 / 上下文重定向 / 设备词覆盖 / 意图守卫。"""

    def _store(self, lang: str) -> RoutingLanguageStore:
        return RoutingLanguageStore(lang)

    async def test_complex_query_delegates_without_macro(self) -> None:
        store = self._store("zh")
        called = False

        class _FakeMacroResolver:
            async def resolve(self, candidates, text, project_id):
                nonlocal called
                called = True
                return ("macro:1", {})

        resolver = IntentResolver(routing_store=store, macro_resolver=_FakeMacroResolver())
        result = await resolver.resolve("复杂查询", "帮我调研一下AI框架对比", 0)
        assert result is None
        assert called is False, "复杂查询意图应直接委派，不应进入宏解析"

    async def test_intent_guard_rejects_guard_miss(self) -> None:
        # en 数据含 time_report 意图守卫：(what|which) (time|day|date|weekday)
        store = self._store("en")
        called = False

        class _FakeMacroResolver:
            async def resolve(self, candidates, text, project_id):
                nonlocal called
                called = True
                return ("macro:time_report", {})

        resolver = IntentResolver(routing_store=store, macro_resolver=_FakeMacroResolver())

        guard_miss = await resolver.resolve("time_report", "打开微信", 0)
        assert guard_miss is None
        assert called is False, "意图守卫未匹配时应拒绝，不应进入宏解析"

        guard_hit = await resolver.resolve("time_report", "what day is today", 0)
        assert guard_hit == ("macro:time_report", {})
        assert called is True, "意图守卫匹配后应继续进入宏解析"

    async def test_device_keyword_redirect_overrides_candidates(self) -> None:
        store = self._store("zh")
        resolver = IntentResolver(routing_store=store)

        candidates = resolver._build_candidates("打开应用", "打开 WiFi")
        assert "打开_WiFi" in candidates, f"设备词应覆盖候选意图: {candidates}"
        assert "关闭_WiFi" in candidates

    async def test_context_redirect_app_specific(self) -> None:
        store = self._store("zh")

        async def music_probe() -> dict:
            return {"app": "Music", "phone_connected": False}

        resolver = IntentResolver(routing_store=store, context_probe=music_probe)
        result = await resolver._redirect_by_context("播放")
        assert result == "播放音乐"

    async def test_context_redirect_phone(self) -> None:
        store = self._store("zh")

        async def phone_probe() -> dict:
            return {"app": "", "phone_connected": True}

        resolver = IntentResolver(routing_store=store, context_probe=phone_probe)
        result = await resolver._redirect_by_context("录制")
        assert result == "手机录屏"

    async def test_context_redirect_default_when_no_match(self) -> None:
        store = self._store("zh")

        async def empty_probe() -> dict:
            return {"app": "UnknownApp", "phone_connected": False}

        resolver = IntentResolver(routing_store=store, context_probe=empty_probe)
        result = await resolver._redirect_by_context("播放")
        assert result == "播放", f"无匹配时应回退到原意图: {result!r}"
