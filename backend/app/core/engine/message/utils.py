"""
Shared message utilities for agent nodes.

Contains common functions for message processing, history repair, and extraction.

This module re-exports functions from specialized sub-modules for backward
compatibility. New code should import directly from the specialized modules.
"""

import logging

from langchain_core.messages import AIMessage, BaseMessage

from app.utils.token import estimate_tokens

logger = logging.getLogger(__name__)


def get_message_text(message) -> str:
    """
    Robustly extract text content from a message object, handling:
    - Normal string content
    - List of blocks (Multimodal/Anthropic)
    """
    if isinstance(message, str):
        return message

    content = message.content
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        # Join all text blocks
        text_parts = []
        for block in content:
            if isinstance(block, str):
                text_parts.append(block)
            elif isinstance(block, dict):
                # Anthropic style: {"type": "text", "text": "..."}
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
        return "\n".join(text_parts)

    return ""


def get_last_human_message(messages: list) -> str | None:
    """Extract the last human message content from a message list."""
    from langchain_core.messages import HumanMessage
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return get_message_text(msg)
    return None


def estimate_message_tokens(msg: BaseMessage) -> int:
    """
    Estimate token count for a single message including structural overhead.

    Uses the unified chars // 4 heuristic from app.utils.token.estimate_tokens.

    Args:
        msg: A LangChain message.

    Returns:
        Estimated token count.
    """
    text = get_message_text(msg)
    base = estimate_tokens(text)
    overhead = 4  # role, name, etc.
    if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
        overhead += 8  # tool_calls have extra overhead
    return base + overhead


def count_total_tokens(messages: list[BaseMessage]) -> int:
    """Sum estimated tokens for all messages (fast path, no model required)."""
    return sum(estimate_message_tokens(m) for m in messages)
