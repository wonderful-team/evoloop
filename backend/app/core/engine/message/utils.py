"""
Shared message utilities for agent nodes.

Contains common functions for message processing, history repair, and extraction.

This module re-exports functions from specialized sub-modules for backward
compatibility. New code should import directly from the specialized modules.
"""

import logging

from app.constants import MAX_OUTPUT_LENGTH
from app.infrastructure.llm.model_profile import get_profile

logger = logging.getLogger(__name__)


def _get_truncate_limit(model: str | None = None) -> int:
    """Get truncate limit from ModelProfile, falling back to MAX_OUTPUT_LENGTH."""
    try:
        profile = get_profile(model) if model else None
        if profile:
            return profile.truncate_limit_chars
    except ImportError:
        pass
    return MAX_OUTPUT_LENGTH


def truncate_message_content(
    content: str,
    limit: int | None = None,
    model: str | None = None,
) -> str:
    """
    Truncate content if it exceeds the limit, adding a metadata footer.
    
    Args:
        content: The content string to truncate.
        limit: Explicit character limit. If None, derived from ModelProfile or MAX_OUTPUT_LENGTH.
        model: Model name for profile-aware limit derivation.
    """
    effective_limit = limit or _get_truncate_limit(model)

    # Use the utility function with custom footer format
    if not content or len(content) <= effective_limit:
        return content

    chars = len(content)
    lines = content.count("\n")
    truncated = content[:effective_limit]
    footer = f"\n...\n[Output truncated: {lines} lines / {chars} chars total. Use specific read/search tools for more.]"
    return truncated + footer


def get_message_text(message) -> str:
    """
    Robustly extract text content from a message object, handling:
    - Normal string content
    - List of blocks (Multimodal/Anthropic)
    """
    from langchain_core.messages import BaseMessage

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


# Backward-compatible re-exports from specialized modules
from app.core.engine.message.forgetting import apply_forgotten_status  # noqa: E402,F401
from app.core.engine.message.folding import fold_messages, to_base_message  # noqa: E402,F401
from app.core.engine.message.repair import prune_trailing_errors, repair_message_history  # noqa: E402,F401
from app.core.engine.message.window import smart_window_slice  # noqa: E402,F401
