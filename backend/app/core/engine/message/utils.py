"""
Shared message utilities for agent nodes.

Contains common functions for message processing, history repair, and extraction.

This module re-exports functions from specialized sub-modules for backward
compatibility. New code should import directly from the specialized modules.
"""

import logging

from app.infrastructure.llm.model_profile import get_profile

logger = logging.getLogger(__name__)


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


# Internal-only re-exports (do not import these from outside ContextTrimmer)
from app.core.engine.message.folding import fold_messages, to_base_message  # noqa: E402,F401
