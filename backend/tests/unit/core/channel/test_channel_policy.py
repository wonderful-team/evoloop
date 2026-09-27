"""OutputChannelPolicy 通道路由真值表 + R3 子代理屏蔽。

对应 ``app/core/channel/policy.py`` 的决策权威：
- 非子代理上下文按 payload 类型 / status / session_source 路由；
- task_type == "subagent" 时所有 payload 一律空集（用户通道不可见，R3），
  该短路发生在 payload 类型判定之前，任何类型（MessageBlock / event/未知）都命中。
"""

from app.core.channel.policy import OutputChannelPolicy
from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.message.constants import MessageStatus
from app.core.engine.message.schemas import MessageBlock, MessageRole

VOICE = "voice"
WEB = "web"
DUTY = "duty"


def _block(
    role: MessageRole,
    status: MessageStatus = MessageStatus.COMPLETED,
) -> MessageBlock:
    return MessageBlock(
        id="m1", thread_id="t", role=role, status=status, content="hi"
    )


class TestMessageBlockRouting:
    def test_ai_completed_on_web_goes_sse_and_mobile(self):
        assert OutputChannelPolicy.resolve(_block(MessageRole.AI), WEB) == {
            "sse",
            "mobile",
        }

    def test_ai_completed_on_voice_adds_voice_channel(self):
        assert OutputChannelPolicy.resolve(_block(MessageRole.AI), VOICE) == {
            "sse",
            "mobile",
            "voice",
        }

    def test_ai_streaming_only_sse_on_web(self):
        assert OutputChannelPolicy.resolve(
            _block(MessageRole.AI, MessageStatus.STREAMING), WEB
        ) == {"sse"}

    def test_ai_completed_duty_without_delegation_stays_sse(self):
        assert OutputChannelPolicy.resolve(_block(MessageRole.AI), DUTY) == {"sse"}

    def test_tool_streaming_only_sse_any_source(self):
        assert OutputChannelPolicy.resolve(
            _block(MessageRole.TOOL, MessageStatus.STREAMING), WEB
        ) == {"sse"}
        assert OutputChannelPolicy.resolve(
            _block(MessageRole.TOOL, MessageStatus.STREAMING), VOICE
        ) == {"sse"}

    def test_tool_completed_sse_and_mobile(self):
        assert OutputChannelPolicy.resolve(_block(MessageRole.TOOL), WEB) == {
            "sse",
            "mobile",
        }

    def test_human_completed_on_mobile_avoids_echo(self):
        assert OutputChannelPolicy.resolve(_block(MessageRole.HUMAN), "mobile") == {
            "sse",
        }

    def test_human_completed_on_web_sse_and_mobile(self):
        assert OutputChannelPolicy.resolve(_block(MessageRole.HUMAN), WEB) == {
            "sse",
            "mobile",
        }

    def test_unknown_payload_defaults_to_sse(self):
        assert OutputChannelPolicy.resolve(object(), WEB) == {"sse"}


class TestR3SubagentIsolation:
    def test_subagent_context_suppresses_all_payload_types(self):
        ctx = EvoContext(thread_id="sub", metadata={"task_type": "subagent"})
        with ContextManager.use(ctx):
            assert OutputChannelPolicy.resolve(_block(MessageRole.AI), VOICE) == set()
            assert OutputChannelPolicy.resolve(_block(MessageRole.TOOL), WEB) == set()
            assert (
                OutputChannelPolicy.resolve(_block(MessageRole.HUMAN), WEB) == set()
            )
            # R3 短路先于 payload 类型判定：未知 payload 同样被屏蔽
            assert OutputChannelPolicy.resolve(object(), WEB) == set()

    def test_non_subagent_metadata_keeps_normal_routing(self):
        ctx = EvoContext(thread_id="main", metadata={"source": WEB})
        with ContextManager.use(ctx):
            assert OutputChannelPolicy.resolve(
                _block(MessageRole.AI, MessageStatus.STREAMING), WEB
            ) == {"sse"}

    def test_no_context_routes_normally(self):
        assert OutputChannelPolicy.resolve(_block(MessageRole.AI), WEB) == {
            "sse",
            "mobile",
        }
