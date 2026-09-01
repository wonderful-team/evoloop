"""OutputChannelPolicy 出站通道选择真值表（纯逻辑，无 LLM/DB 依赖）。

单 Agent ReAct 架构下不再按 node_source（supervisor/worker/finish）区分通道——
只有一个主 Agent 节点，子代理消息由 ``resolve()`` 按 ``task_type == "subagent"``
整体屏蔽（R3）。本测试覆盖 app/core/channel/policy.py 文档中的真值表：
voice/web/mobile 会话 × 流式/终态 MessageBlock、Tool/Human 块、系统事件。
"""

from __future__ import annotations

import pytest

from app.core.channel.policy import OutputChannelPolicy
from app.core.engine.message.schemas import MessageBlock
from app.core.events.base import BaseEvent
from app.models.schemas.events import ProgressEvent, ThinkingEvent, TokenEvent

pytestmark = pytest.mark.unit


def _block(role: str, status: str) -> MessageBlock:
    return MessageBlock(
        id=f"msg-{role}-{status}", role=role, content="x", status=status, thread_id="t"
    )


class TestTokenRouting:
    """TokenEvent / ThinkingEvent / ProgressEvent 路由。"""

    async def test_voice_tokens_go_to_voice(self) -> None:
        for ev in (TokenEvent(content="x"), ThinkingEvent(content="x"), ProgressEvent()):
            assert OutputChannelPolicy.resolve(ev, "voice") == {"sse", "voice"}

    async def test_web_tokens_sse_only(self) -> None:
        assert OutputChannelPolicy.resolve(TokenEvent(content="x"), "web") == {"sse"}
        assert OutputChannelPolicy.resolve(TokenEvent(content="x"), "mobile") == {"sse"}
        assert OutputChannelPolicy.resolve(TokenEvent(content="x"), None) == {"sse"}


class TestAIMessageBlockRouting:
    """AI MessageBlock：流式/终态 × 会话来源。"""

    async def test_ai_streaming_voice(self) -> None:
        assert OutputChannelPolicy.resolve(_block("ai", "streaming"), "voice") == {"sse", "voice"}

    async def test_ai_streaming_web(self) -> None:
        assert OutputChannelPolicy.resolve(_block("ai", "streaming"), "web") == {"sse"}

    async def test_ai_completed_voice(self) -> None:
        assert OutputChannelPolicy.resolve(_block("ai", "completed"), "voice") == {"sse", "mobile", "voice"}

    async def test_ai_completed_web(self) -> None:
        assert OutputChannelPolicy.resolve(_block("ai", "completed"), "web") == {"sse", "mobile"}


class TestToolAndHumanBlocks:
    """Tool / Human MessageBlock 路由。"""

    async def test_tool_streaming_sse_only(self) -> None:
        assert OutputChannelPolicy.resolve(_block("tool", "streaming"), "voice") == {"sse"}

    async def test_tool_completed_goes_to_mobile(self) -> None:
        assert OutputChannelPolicy.resolve(_block("tool", "completed"), "web") == {"sse", "mobile"}

    async def test_human_mobile_echo_suppressed(self) -> None:
        assert OutputChannelPolicy.resolve(_block("human", "completed"), "mobile") == {"sse"}

    async def test_human_web_goes_to_mobile(self) -> None:
        assert OutputChannelPolicy.resolve(_block("human", "completed"), "web") == {"sse", "mobile"}


class TestBaseEventRouting:
    """系统事件路由（SessionCompleted 等）。"""

    async def test_public_event_voice(self) -> None:
        ev = BaseEvent(event_type="agent.run_completed", source="voice", is_public=True)
        assert OutputChannelPolicy.resolve(ev, "voice") == {"sse", "voice"}

    async def test_public_event_web(self) -> None:
        ev = BaseEvent(event_type="agent.run_completed", source="web", is_public=True)
        assert OutputChannelPolicy.resolve(ev, "web") == {"sse"}

    async def test_event_prefers_own_source(self) -> None:
        ev = BaseEvent(event_type="agent.run_completed", source="voice", is_public=True)
        assert OutputChannelPolicy.resolve(ev, "web") == {"sse", "voice"}
