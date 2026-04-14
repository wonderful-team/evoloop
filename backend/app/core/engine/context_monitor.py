"""
Context Monitor - Real-time context usage monitoring for Agent.

Provides context statistics to help Agent make informed decisions about
context management, including when to use forget_tool_outputs.
"""

import logging
from typing import Optional

from langchain_core.messages import (
    BaseMessage,
    ToolMessage,
)
from pydantic import Field

from app.constants import (
    CONTEXT_WARNING_THRESHOLD,
    CONTEXT_CRITICAL_THRESHOLD,
    DEFAULT_CONTEXT_LIMIT,
)
from app.core.engine.message_utils import get_message_text
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class ToolCallInfo(DynamicBaseModel):
    """Information about a recent tool call."""
    tool_call_id: str
    name: str
    timestamp: float
    char_count: int


class ContextStats(DynamicBaseModel):
    """
    Context usage statistics for Agent awareness.
    """
    total_chars: int
    max_chars: int
    message_count: int
    tool_message_count: int
    tool_chars: int
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
            f"Usage: {self.total_chars:,} / {self.max_chars:,} chars ({usage_pct:.0f}%) - {status}",
            f"Messages: {self.message_count} total, {self.tool_message_count} tool outputs ({self.tool_chars:,} chars)",
        ]

        if self.recent_tools:
            recent_names = [f"{t.name}({t.char_count//1000}k)" for t in self.recent_tools[-5:]]
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

    def suggest_forgetting(self) -> list[str]:
        """
        Identify tool_call_ids that should be forgotten to free space.
        Only considers tools older than FORGET_SAFETY_WINDOW.
        """
        if not self.is_near_limit():
            return []
            
        # Filter for candidates

        # We need the full list from stats, which calculate() produces
        # But stats only has last 5. We need to find them from the messages.
        return [] # Logic moved to calculate or similar


class ContextMonitor:
    """Monitors and reports context usage for Agent awareness."""

    @staticmethod
    def calculate(
        messages: list[BaseMessage],
        max_chars: Optional[int] = None,
    ) -> ContextStats:
        """
        Calculate context statistics from message list.

        Args:
            messages: Current message history
            max_chars: Maximum context size (defaults to DEFAULT_CONTEXT_LIMIT)

        Returns:
            ContextStats with usage information
        """
        if max_chars is None:
            max_chars = DEFAULT_CONTEXT_LIMIT

        total_chars = 0
        tool_chars = 0
        tool_count = 0
        recent_tools: list[ToolCallInfo] = []

        for i, msg in enumerate(messages):
            text = get_message_text(msg)
            char_count = len(text)
            total_chars += char_count

            if isinstance(msg, ToolMessage):
                tool_count += 1
                tool_chars += char_count

                # Track recent tools (last 5)
                recent_tools.append(ToolCallInfo(
                    tool_call_id=msg.tool_call_id,
                    name=msg.name or "unknown",
                    timestamp=float(i),  # Use index as timestamp proxy
                    char_count=char_count,
                ))

        # Keep only last 5 tools
        recent_tools_summary = recent_tools[-5:]

        usage_ratio = min(total_chars / max_chars, 1.0) if max_chars > 0 else 0.0

        return ContextStats(
            total_chars=total_chars,
            max_chars=max_chars,
            message_count=len(messages),
            tool_message_count=tool_count,
            tool_chars=tool_chars,
            recent_tools=recent_tools_summary,
            usage_ratio=usage_ratio,
        )

    @staticmethod
    def inject_into_prompt(
        system_prompt: str,
        messages: list[BaseMessage],
        max_chars: Optional[int] = None,
    ) -> str:
        """
        Inject context stats into system prompt.

        Args:
            system_prompt: Original system prompt
            messages: Current message history
            max_chars: Maximum context size

        Returns:
            System prompt with context monitor section appended
        """
        stats = ContextMonitor.calculate(messages, max_chars)
        stats_section = stats.to_prompt()

        # Insert before any closing sections if present
        # Otherwise append at the end
        return f"{system_prompt}\n\n{stats_section}"


def get_context_status_for_agent(
    messages: list[BaseMessage],
    max_chars: Optional[int] = None,
) -> dict:
    """
    Get context status as a dict for programmatic use.

    Returns:
        Dict with status information suitable for tool use
    """
    stats = ContextMonitor.calculate(messages, max_chars)

    return {
        "total_chars": stats.total_chars,
        "max_chars": stats.max_chars,
        "usage_percent": round(stats.usage_ratio * 100, 1),
        "message_count": stats.message_count,
        "tool_count": stats.tool_message_count,
        "tool_chars": stats.tool_chars,
        "status": "critical" if stats.is_critical() else "warning" if stats.is_near_limit() else "ok",
        "recent_tools": [
            {"name": t.name, "chars": t.char_count}
            for t in stats.recent_tools
        ],
    }
