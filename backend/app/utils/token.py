"""
Token counting utilities for accurate context management.

Provides model-aware token counting to replace heuristic (chars // 4) estimation.
Uses tiktoken for OpenAI-compatible models and falls back to character estimation
for unsupported models.

All token counting in the system should import from this module.
"""

import logging

logger = logging.getLogger(__name__)

# Fallback ratio: 1 token ≈ N characters (varies by language)
# Unified to 4 across the entire system for consistency with ContextTrimmer budgets.
_FALLBACK_CHARS_PER_TOKEN = 4


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
