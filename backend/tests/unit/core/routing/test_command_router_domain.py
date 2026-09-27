"""域路由（predeclared_domain / skip_l0）单元测试。

覆盖：
- host_declared 域跳过 L1 分类（不调 BERT）直接 delegate
- skip_l0 + L1 低置信 → ambiguous 兜底
- 路由决策的 IntentHint 形状（供 hydrate/ToolsManager 消费）
"""

from unittest.mock import patch

import pytest

from app.core.routing import constants as routing_constants
from app.core.routing.command_router import CommandRouter


@pytest.fixture
def router():
    return CommandRouter()


@pytest.mark.asyncio
async def test_predeclared_domain_skips_l1_classifier(router):
    with patch("app.core.routing.domain_classifier.predict") as mock_predict:
        decision = await router.resolve(
            "各商品售价是多少？",
            thread_id="test-predeclared-1",
            source="web",
            skip_l0=True,
            predeclared_domain="mall_ops",
        )
    mock_predict.assert_not_called()  # 路由声明取代分类推理
    assert decision.status == "delegate"
    assert decision.target_type == "agent"
    assert decision.confidence == 1.0
    assert decision.intent_hint.domain == "mall_ops"
    assert decision.intent_hint.intent == routing_constants.INTENT_DOMAIN_CLASSIFIED
    assert "host declared" in decision.intent_hint.reason


@pytest.mark.asyncio
async def test_skip_l0_low_confidence_delegates_as_ambiguous(router):
    with (
        patch("app.core.routing.domain_classifier.predict", return_value=(None, 0.0)),
    ):
        decision = await router.resolve(
            "随便聊点什么",
            thread_id="test-amb-1",
            source="web",
            skip_l0=True,
        )
    assert decision.status == "delegate"
    assert decision.target_type == "agent"
    assert decision.intent_hint.domain == routing_constants.DOMAIN_AMBIGUOUS


@pytest.mark.asyncio
async def test_skip_l0_classified_domain_carries_label(router):
    with (
        patch(
            "app.core.routing.domain_classifier.predict",
            return_value=("ecommerce", 0.93),
        ),
    ):
        decision = await router.resolve(
            "帮我看看商品",
            thread_id="test-cls-1",
            source="web",
            skip_l0=True,
        )
    assert decision.target_type == "agent"
    assert decision.intent_hint.domain == "ecommerce"
    assert decision.intent_hint.confidence == pytest.approx(0.93)


@pytest.mark.asyncio
async def test_predeclared_domain_records_thread_state(router):
    # 状态记录副作用保留：下一轮指代消解（它/这个/刚才）依赖 previous_intent
    await router.resolve(
        "看看商品",
        thread_id="test-state-1",
        source="web",
        skip_l0=True,
        predeclared_domain="mall_ops",
    )
    from app.core.routing.conversation_state import _get_thread_intent_state

    previous_intent, history = _get_thread_intent_state("test-state-1")
    assert previous_intent == "mall_ops"
    assert history and history[-1] == "看看商品"
