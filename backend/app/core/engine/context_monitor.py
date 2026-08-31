"""
Context Monitor — Real-time context usage monitoring for Agent.

Provides context statistics (in **tokens**) to help the Agent track its budget;
上下文裁剪/工具输出折叠由系统自动管理（ContextTrimmer + executor 统一截断）。

All metrics are token-based and aligned with ContextTrimmer budgets.
"""

from app.constants import DEFAULT_MAX_CONTEXT_TOKENS
from app.core.engine.message.native_classes import BaseMessage, ToolMessage
from app.core.engine.message.utils import estimate_message_tokens
from app.core.engine.schemas import ContextStats, ToolCallInfo
from app.infrastructure.llm.platform_service import llm_platform_service


class ContextMonitor:
    """Monitors and reports context usage for Agent awareness (token-based)."""

    @staticmethod
    def calculate(
        messages: list[BaseMessage], model: str | None = None
    ) -> ContextStats:
        """
        Calculate context statistics from message list (token-based).

        Args:
            messages: Current message history
            model: Explicit model name. If not provided, uses a safe default.

        Returns:
            ContextStats with token-based usage information
        """
        if not model:
            max_tokens = DEFAULT_MAX_CONTEXT_TOKENS
        else:
            profile = llm_platform_service.get_profile(model)
            max_tokens = profile.max_context_tokens

        total_tokens = 0
        tool_tokens = 0
        tool_count = 0
        recent_tools: list[ToolCallInfo] = []

        for i, msg in enumerate(messages):
            msg_tokens = estimate_message_tokens(msg)
            total_tokens += msg_tokens

            if isinstance(msg, ToolMessage):
                tool_count += 1
                tool_tokens += msg_tokens

                # Track recent tools (last 5)
                recent_tools.append(
                    ToolCallInfo(
                        tool_call_id=msg.tool_call_id,
                        name=msg.name,
                        timestamp=float(i),  # Use index as timestamp proxy
                        token_count=msg_tokens,
                    )
                )

        # Keep only last 5 tools
        recent_tools_summary = recent_tools[-5:]

        usage_ratio = min(total_tokens / max_tokens, 1.0) if max_tokens > 0 else 0.0

        return ContextStats(
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            message_count=len(messages),
            tool_message_count=tool_count,
            tool_tokens=tool_tokens,
            recent_tools=recent_tools_summary,
            usage_ratio=usage_ratio,
        )
