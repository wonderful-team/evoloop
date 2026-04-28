"""
Reasoning content — single source of truth for thinking data.

This module provides:
1. Monkey-patch for langchain-openai to capture reasoning_content from streaming deltas
2. Extraction from LangChain messages / additional_kwargs
3. DB serialization / deserialization

Import order constraint:
    The monkey-patch must be applied BEFORE any ChatOpenAI instances are created.
    LLM factory imports this module at startup to ensure the patch is active.
"""

import json
import logging
from typing import Any

from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. Monkey-patch (must run before any ChatOpenAI instantiation)
# ---------------------------------------------------------------------------


def _apply_reasoning_patch() -> None:
    """Apply monkey-patch to langchain_openai for reasoning_content support."""
    try:
        import langchain_openai.chat_models.base as base_module
        from langchain_core.messages import AIMessageChunk

        _original_convert = base_module._convert_delta_to_message_chunk

        def _convert_delta_with_reasoning(_dict, default_class):
            result = _original_convert(_dict, default_class)
            if reasoning := _dict.get("reasoning_content"):
                if isinstance(result, AIMessageChunk):
                    result.additional_kwargs["reasoning_content"] = (
                        result.additional_kwargs.get("reasoning_content", "") + reasoning
                    )
            return result

        base_module._convert_delta_to_message_chunk = _convert_delta_with_reasoning
        logger.info("[Reasoning] Applied _convert_delta_to_message_chunk patch")

    except Exception as e:
        logger.warning(f"[Reasoning] Failed to apply patch: {e}")


# Auto-apply on module import
_apply_reasoning_patch()


# ---------------------------------------------------------------------------
# 2. Extraction
# ---------------------------------------------------------------------------


def extract_reasoning_string(msg: BaseMessage) -> str | None:
    """Extract raw reasoning_content string from a LangChain BaseMessage."""
    return extract_reasoning_from_kwargs(getattr(msg, "additional_kwargs", None))


def extract_reasoning_from_kwargs(additional_kwargs: dict | None) -> str | None:
    """Extract raw reasoning_content string from additional_kwargs dict."""
    if not additional_kwargs:
        return None
    reasoning = additional_kwargs.get("reasoning_content")
    return str(reasoning).strip() if reasoning else None


def to_thinking_blocks(msg: BaseMessage) -> list[dict[str, Any]] | None:
    """Extract structured thinking blocks [{"type": "reasoning", "content": "..."}] from a BaseMessage."""
    reasoning = extract_reasoning_string(msg)
    if reasoning:
        return [{"type": _THINKING_TYPE, "content": reasoning}]
    return None


# ---------------------------------------------------------------------------
# 3. Thinking block construction (for MessageBlock / SSE / Mobile)
# ---------------------------------------------------------------------------


_THINKING_TYPE: str = "reasoning"


def build_thinking_blocks(raw_reasoning: str | None) -> list[dict[str, Any]] | None:
    """Build structured thinking blocks from a raw reasoning_content string."""
    if not raw_reasoning:
        return None
    return [{"type": _THINKING_TYPE, "content": raw_reasoning}]


def infer_thinking_type(metadata: dict | None) -> str | None:
    """Infer thinking type from message metadata. Returns 'reasoning' if metadata contains reasoning_content."""
    if metadata and metadata.get("reasoning_content"):
        return _THINKING_TYPE
    return None


# ---------------------------------------------------------------------------
# 4. DB Serialization / Deserialization
# ---------------------------------------------------------------------------


def parse_thinking(raw: str | None) -> list[dict[str, Any]] | None:
    """Parse JSON-serialized thinking from DB string into structured list[dict]."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    return None


def serialize_thinking(thinking: list[dict[str, Any]] | None) -> str | None:
    """Serialize structured thinking list[dict] into JSON string for DB storage."""
    if not thinking:
        return None
    return json.dumps(thinking, ensure_ascii=False)


def wrap_reasoning_for_db(reasoning: str | None) -> str | None:
    """Wrap raw reasoning_content string as structured JSON list for DB storage."""
    if not reasoning:
        return None
    return json.dumps([{"type": _THINKING_TYPE, "content": reasoning}], ensure_ascii=False)
