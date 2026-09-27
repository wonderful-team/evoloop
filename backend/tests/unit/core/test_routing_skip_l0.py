"""文字（web）跳过 L0、只走 L1 的确定性单元测试。

验证两条通道的分叉：
- web 源：``dispatch_user_message`` 以 ``skip_l0=True`` 调用 ``command_router.resolve``，
  ``resolve`` 完全跳过 L0 匹配层（导航宏/模板宏/BERT 本地动作/复合意图），
  直接走 L1 领域分类器 → 委派 Agent。
- voice 源：``skip_l0=False``，L0 匹配层保持原行为（BERT 命中宏仍本地路由）。

全部为进程内确定性测试，不依赖后端服务、ONNX 模型与 LLM。
"""

from __future__ import annotations

import pytest

from app.core.channel.base import IncomingMessage
from app.core.routing import command_router as cr
from app.core.routing.command_router import CommandRouter
from app.core.routing.dispatch_handler import dispatch_user_message
from app.core.routing.schemas import RouteDecision


@pytest.fixture(autouse=True)
def _no_navigation_macro(monkeypatch: pytest.MonkeyPatch):
    """L0 导航宏解析：恒未命中（避免 DB 依赖）。"""
    from app.core.learning.macro.service import MacroService

    async def _none(_text: str) -> None:
        return None

    monkeypatch.setattr(MacroService, "resolve_navigation_macro", _none)


class _MacroIntentResolver:
    """L0 IntentResolver：恒返回一个宏匹配。"""

    async def resolve(self, _intent_name: str, _text: str, _project_id: int):
        return ("macro:123", {})


class _NoDeviceMap:
    """L0 设备上下文映射：恒无设备信息（避免 DB 依赖）。"""

    async def device_of(self, _macro_id: int):
        return None

    async def phone_twin(self, _macro_id: int):
        return None


def _make_router() -> CommandRouter:
    return CommandRouter(
        intent_resolver=_MacroIntentResolver(),
    )


class TestCommandRouterSkipL0:
    """``command_router.resolve`` 的 skip_l0 门控。"""

    async def test_web_skip_l0_never_touches_l0_and_delegates_to_l1(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        router = _make_router()
        l1_calls: list[dict] = []

        async def _fake_l1_delegate(text, _session_history, source, **_kwargs):
            l1_calls.append({"text": text, "source": source})
            return RouteDecision(
                status="delegate",
                target_type="agent",
                target={"type": "agent"},
                source=source,
                raw="ambiguous",
            )

        monkeypatch.setattr(router, "_l1_delegate", _fake_l1_delegate)

        async def _l0_should_not_run(*_args, **_kwargs):
            pytest.fail("web 源不应进入 L0 匹配层")

        monkeypatch.setattr(cr.matcher_cache, "get_local_matcher", _l0_should_not_run)
        monkeypatch.setattr(cr, "is_compound_intent", _l0_should_not_run)
        monkeypatch.setattr(cr, "classifier_predict", _l0_should_not_run)
        monkeypatch.setattr(
            router._intent_resolver, "resolve", _l0_should_not_run
        )

        decision = await router.resolve(
            "麻烦对对对",
            thread_id="t-web",
            project_id=0,
            source="web",
            skip_l0=True,
        )

        assert l1_calls == [{"text": "麻烦对对对", "source": "web"}]
        assert decision.target_type == "agent"
        assert decision.status == "delegate"

    async def test_voice_keeps_l0_macro_hit_routing_locally(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """语音源 L0 命中宏 → 仍本地路由（target_type=macro），不受 skip_l0 影响。"""
        router = _make_router()
        l1_calls: list = []

        async def _fake_l1_delegate(text, _session_history, source, **_kwargs):
            l1_calls.append(text)
            return RouteDecision(
                status="delegate",
                target_type="agent",
                target={"type": "agent"},
                source=source,
            )

        monkeypatch.setattr(router, "_l1_delegate", _fake_l1_delegate)

        class _NoMatcher:
            def match(self, text, project_id=0):
                return None

        async def _get_no_matcher():
            return _NoMatcher()

        monkeypatch.setattr(cr.matcher_cache, "get_local_matcher", _get_no_matcher)
        monkeypatch.setattr(cr, "is_compound_intent", lambda text: False)
        monkeypatch.setattr(cr, "classifier_predict", lambda text: ("ack", 0.77))
        monkeypatch.setattr(cr, "get_macro_device_map", lambda: _NoDeviceMap())

        decision = await router.resolve(
            "麻烦对对对",
            thread_id="t-voice",
            project_id=0,
            source="voice",
            skip_l0=False,
        )

        assert l1_calls == [], "语音源 L0 命中宏时不应进入 L1"
        assert decision.target_type == "macro"
        assert decision.target == {"type": "macro", "id": 123}


class TestDispatchSkipL0Wiring:
    """``dispatch_user_message`` 按 source 传递 skip_l0。"""

    class _FakeChannel:
        """最小 InputChannel：receive 返回一条消息，dispatch 直接返回 inputs。"""

        def __init__(self) -> None:
            self.dispatched: list[IncomingMessage] = []

        async def receive(self, raw: dict, context=None, member_id: int = 0):
            return IncomingMessage(
                source=raw.get("source", "web"),
                thread_id=raw["thread_id"],
                text=raw["text"],
                project_id=int(raw.get("project_id", 0)),
                context=context,
                member_id=member_id,
            )

        async def dispatch(self, msg: IncomingMessage):
            self.dispatched.append(msg)
            return {"messages": [{"role": "user", "content": msg.text}]}

    async def _run(self, monkeypatch: pytest.MonkeyPatch, source: str) -> tuple[dict, dict]:
        from app.core.routing import dispatch_handler

        captured: dict = {}

        async def _fake_resolve(text, *, source, skip_l0=False, **_kwargs):
            captured.update(
                {
                    "text": text,
                    "source": source,
                    "skip_l0": skip_l0,
                }
            )
            return RouteDecision(
                status="delegate",
                target_type="agent",
                target={"type": "agent"},
                source=source,
            )

        monkeypatch.setattr(dispatch_handler.command_router, "resolve", _fake_resolve)

        channel = self._FakeChannel()
        await dispatch_user_message(
            {
                "thread_id": "t-1",
                "text": "麻烦对对对",
                "project_id": 0,
                "source": source,
            },
            source=source,
            input_channel=channel,
            thread_id="t-1",
            project_id=0,
            member_id=0,
            context=None,
        )
        return captured, {"channel": channel}

    async def test_web_passes_skip_l0_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured, _ = await self._run(monkeypatch, "web")
        assert captured["source"] == "web"
        assert captured["skip_l0"] is True

    async def test_voice_passes_skip_l0_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured, _ = await self._run(monkeypatch, "voice")
        assert captured["source"] == "voice"
        assert captured["skip_l0"] is False

    async def test_mobile_passes_skip_l0_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """移动端文字链路与 web 一致：跳过 L0，走 L1 领域分类 → Agent。"""
        captured, _ = await self._run(monkeypatch, "mobile")
        assert captured["source"] == "mobile"
        assert captured["skip_l0"] is True


class TestInjectionVoiceOnly:
    """[前置上下文] 注入只服务 voice，web 文字消息不得注入（防跨订单串单）。"""

    @staticmethod
    async def _dispatch_with_macro_result(
        monkeypatch: pytest.MonkeyPatch, source: str
    ) -> str:
        from app.core.routing import dispatch_handler
        from app.core.routing.conversation_state import conversation_state

        async def _fake_resolve(_text, *, source, _skip_l0=False, **_kwargs):
            return RouteDecision(
                status="delegate",
                target_type="agent",
                target={"type": "agent"},
                source=source,
            )

        monkeypatch.setattr(dispatch_handler.command_router, "resolve", _fake_resolve)

        # 模拟同一线程上一轮语音 L0 宏已执行（只存内存、不落库）
        conversation_state.set_last_macro_result(
            "t-order", "已执行宏「处理退款单389」：退款 ¥32.90 到账"
        )
        try:
            channel = TestDispatchSkipL0Wiring._FakeChannel()
            await dispatch_user_message(
                {
                    "thread_id": "t-order",
                    "text": "处理退款单 202608160702156507（order_goods 390，仅退款 ¥71.80）",
                    "project_id": 0,
                    "source": source,
                },
                source=source,
                input_channel=channel,
                thread_id="t-order",
                project_id=0,
                member_id=0,
                context=None,
            )
            return channel.dispatched[0].text
        finally:
            conversation_state.clear("t-order")

    async def test_web_message_not_injected_with_l0_macro_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """web 文字消息即使同一线程有语音宏执行记录，也不注入 [前置上下文]。"""
        text = await self._dispatch_with_macro_result(monkeypatch, "web")
        assert text == (
            "处理退款单 202608160702156507（order_goods 390，仅退款 ¥71.80）"
        ), f"web 不应注入语音宏上下文: {text!r}"

    async def test_voice_message_still_injected_with_l0_macro_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """voice 消息保持原行为：注入 [前置上下文] 让 Agent 得知上一轮宏执行结果。"""
        text = await self._dispatch_with_macro_result(monkeypatch, "voice")
        assert text.startswith("[前置上下文] "), f"voice 应注入前置上下文: {text!r}"
        assert "处理退款单389" in text
