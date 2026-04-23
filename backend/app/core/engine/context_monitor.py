"""
Context Monitor — Real-time context usage monitoring for Agent.

Provides context statistics (in **tokens**) to help Agent make informed decisions
about context management, including when to use forget_tool_outputs.

All metrics are token-based and aligned with ContextTrimmer budgets.
"""

import logging

from langchain_core.messages import (
    BaseMessage,
    ToolMessage,
)
from pydantic import Field

from app.constants import DEFAULT_MAX_CONTEXT_TOKENS
from app.core.engine.message.utils import estimate_message_tokens
from app.infrastructure.llm.model_profile import get_profile
from app.infrastructure.pydantic_base import DynamicBaseModel

# Context usage thresholds (pure ratios, unit-agnostic)
CONTEXT_WARNING_THRESHOLD = 0.80
CONTEXT_CRITICAL_THRESHOLD = 0.95

logger = logging.getLogger(__name__)


class ToolCallInfo(DynamicBaseModel):
    """Information about a recent tool call."""
    tool_call_id: str
    name: str
    timestamp: float
    token_count: int


class ContextStats(DynamicBaseModel):
    """
    Context usage statistics for Agent awareness (token-based).
    """
    total_tokens: int
    max_tokens: int
    message_count: int
    tool_message_count: int
    tool_tokens: int
    recent_tools: list[ToolCallInfo] = Field(default_factory=list)
    usage_ratio: float

    def to_prompt(self) -> str:
        """Format as a concise prompt section for System Prompt injection."""
        usage_pct = self.usage_ratio * 100

        # Status indicator
        if self.usage_ratio >= CONTEXT_CRITICAL_THRESHOLD:
            status = "🔴 CRITICAL - Context nearly full!"
        elif self.usage_ratio >= CONTEXT_WARNING_THRESHOLD:
            status = "⚠️  WARNING - Consider freeing space"
        else:
            status = "✅ OK"

        lines = [
            "[Context Monitor]",
            f"Usage: {self.total_tokens:,} / {self.max_tokens:,} tokens ({usage_pct:.0f}%) - {status}",
            f"Messages: {self.message_count} total, {self.tool_message_count} tool outputs ({self.tool_tokens:,} tokens)",
        ]

        if self.recent_tools:
            recent_names = [f"{t.name}({t.token_count//1000}k)" for t in self.recent_tools[-5:]]
            lines.append(f"Recent tools: {', '.join(recent_names)}")

        # Add guidance when approaching limit
        if self.usage_ratio >= CONTEXT_WARNING_THRESHOLD:
            lines.append("Tip: Use forget_tool_outputs to fold old exploration steps")

        return "\n".join(lines)

    def is_near_limit(self) -> bool:
        """Check if context is approaching limit."""
        return self.usage_ratio >= CONTEXT_WARNING_THRESHOLD

    def is_critical(self) -> bool:
        """Check if context is critically full."""
        return self.usage_ratio >= CONTEXT_CRITICAL_THRESHOLD


class ContextMonitor:
    """Monitors and reports context usage for Agent awareness (token-based)."""

    @staticmethod
    def calculate(messages: list[BaseMessage], model: str | None = None) -> ContextStats:
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
            profile = get_profile(model)
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
                recent_tools.append(ToolCallInfo(
                    tool_call_id=msg.tool_call_id,
                    name=msg.name or "unknown",
                    timestamp=float(i),  # Use index as timestamp proxy
                    token_count=msg_tokens,
                ))

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

    @staticmethod
    def inject_into_prompt(
        system_prompt: str,
        messages: list[BaseMessage],
        model: str | None = None,
    ) -> str:
        """
        Inject context stats into system prompt.

        Args:
            system_prompt: Original system prompt
            messages: Current message history
            model: Explicit model name

        Returns:
            System prompt with context monitor section appended
        """
        stats = ContextMonitor.calculate(messages, model=model)
        stats_section = stats.to_prompt()

        # Insert before any closing sections if present
        # Otherwise append at the end
        return f"{system_prompt}\n\n{stats_section}"


def get_context_status_for_agent(messages: list[BaseMessage], model: str | None = None) -> dict:
    """
    Get context status as a dict for programmatic use.

    Args:
        messages: Current message history
        model: Explicit model name

    Returns:
        Dict with token-based status information suitable for tool use
    """
    stats = ContextMonitor.calculate(messages, model=model)

    return {
        "total_tokens": stats.total_tokens,
        "max_tokens": stats.max_tokens,
        "usage_percent": round(stats.usage_ratio * 100, 1),
        "message_count": stats.message_count,
        "tool_count": stats.tool_message_count,
        "tool_tokens": stats.tool_tokens,
        "status": "critical" if stats.is_critical() else "warning" if stats.is_near_limit() else "ok",
        "recent_tools": [
            {"name": t.name, "tokens": t.token_count}
            for t in stats.recent_tools
        ],
    }
