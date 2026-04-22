"""
Token counting utilities for accurate context management.

Provides model-aware token counting to replace heuristic (chars // 4) estimation.
Uses tiktoken for OpenAI-compatible models and falls back to character estimation
for unsupported models.

All token counting in the system should import from this module.
"""

import logging
from functools import lru_cache

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
)

logger = logging.getLogger(__name__)

# Model -> tiktoken encoding mapping
_MODEL_ENCODING_MAP: dict[str, str] = {
    # GPT-4o family
    "gpt-4o": "o200k_base",
    "gpt-4o-mini": "o200k_base",
    # GPT-4 family
    "gpt-4": "cl100k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-4-turbo-preview": "cl100k_base",
    # GPT-3.5 family
    "gpt-3.5-turbo": "cl100k_base",
    # Claude family (use cl100k_base as best approximation)
    "claude-3-opus": "cl100k_base",
    "claude-3-sonnet": "cl100k_base",
    "claude-3-haiku": "cl100k_base",
    "claude-3.5-sonnet": "cl100k_base",
    "claude-3.5-haiku": "cl100k_base",
}

# Fallback ratio: 1 token ≈ N characters (varies by language)
# Unified to 4 across the entire system for consistency with ContextTrimmer budgets.
_FALLBACK_CHARS_PER_TOKEN = 4


@lru_cache(maxsize=8)
def _get_encoder(encoding_name: str):
    """Lazily load and cache tiktoken encoder."""
    try:
        import tiktoken
        return tiktoken.get_encoding(encoding_name)
    except ImportError:
        logger.warning("tiktoken not installed. Using character-based estimation. Install with: pip install tiktoken")
        return None
    except Exception as e:
        logger.warning(f"Failed to load tiktoken encoding '{encoding_name}': {e}")
        return None


def get_encoding_for_model(model: str) -> str | None:
    """
    Map a model name to its tiktoken encoding.
    Supports fuzzy matching for model variants (e.g. "gpt-4o-2024-05-13" -> "o200k_base").

    Returns None if no mapping found.
    """
    # Exact match
    if model in _MODEL_ENCODING_MAP:
        return _MODEL_ENCODING_MAP[model]

    # Fuzzy match: try prefix matching (handles versioned model names)
    model_lower = model.lower()
    for known_model, encoding in _MODEL_ENCODING_MAP.items():
        if model_lower.startswith(known_model):
            return encoding

    return None


# ---------------------------------------------------------------------------
# Precise counting (use when model is known)
# ---------------------------------------------------------------------------

def count_tokens(text: str, model: str) -> int:
    """
    Count tokens in a text string.

    Uses tiktoken for supported models, falls back to character estimation.

    Args:
        text: The text to count tokens for.
        model: The model name to use for encoding selection.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0

    encoding_name = get_encoding_for_model(model)
    if encoding_name:
        encoder = _get_encoder(encoding_name)
        if encoder:
            return len(encoder.encode(text))

    # Fallback: character-based estimation
    return int(len(text) / _FALLBACK_CHARS_PER_TOKEN)


def _message_to_text(msg: BaseMessage) -> str:
    """Extract text content from a message for precise token counting."""
    content = msg.content
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        # Multimodal: only count text blocks
        text = "\n".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    else:
        text = str(content)

    # Account for tool_calls overhead in AIMessages
    if isinstance(msg, AIMessage) and msg.tool_calls:
        for tc in msg.tool_calls:
            text += f"\n{tc.get('name', '')}\n{str(tc.get('args', {}))}"

    return text


def count_messages_tokens(messages: list[BaseMessage], model: str) -> int:
    """
    Count total tokens across a list of messages.

    Includes a per-message overhead (~4 tokens for role/separators)
    matching OpenAI's token counting methodology.

    Args:
        messages: List of LangChain messages.
        model: The model name for encoding selection.

    Returns:
        Total estimated token count.
    """
    if not messages:
        return 0

    total = 0
    per_message_overhead = 4  # role + separators

    for msg in messages:
        text = _message_to_text(msg)
        total += count_tokens(text, model) + per_message_overhead

    # Final assistant reply priming (~3 tokens)
    total += 3

    return total


# ---------------------------------------------------------------------------
# Fast estimation (use when model is unknown or for high-frequency calls)
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """
    Fast token estimation without model info.

    Uses chars // 4 heuristic. Guaranteed to return >= 1 for non-empty text.
    This is the unified estimation used by ContextTrimmer and context_monitor.

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count (0 for empty, >= 1 otherwise).
    """
    if not text:
        return 0
    return max(1, len(text) // _FALLBACK_CHARS_PER_TOKEN)
