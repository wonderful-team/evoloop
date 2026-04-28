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

from __future__ import annotations
import json
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.engine.message.schemas import ThinkingBlock

from langchain_core.messages import BaseMessage, AIMessageChunk


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


def extract_reasoning_from_chunk(chunk: Any) -> str | None:
    """从 LangChain 流式 Chunk 中提取推理内容"""
    if not hasattr(chunk, "message"):
        return None
    
    msg_chunk = chunk.message
    if not isinstance(msg_chunk, AIMessageChunk):
        return None
        
    return extract_reasoning_from_kwargs(msg_chunk.additional_kwargs)


def extract_reasoning_from_message(message: BaseMessage) -> str | None:
    """从完整的 LangChain 消息中提取推理内容 (支持 Kimi/OpenAI 格式)"""
    # 1. 尝试从 additional_kwargs 提取 (如 kimi-k2-thinking-turbo)
    reasoning = extract_reasoning_from_kwargs(message.additional_kwargs)
    if reasoning:
        return reasoning
            
    return None


def extract_reasoning_from_kwargs(additional_kwargs: dict | None) -> str | None:
    """Extract raw reasoning_content string from additional_kwargs dict."""
    if not additional_kwargs:
        return None
    reasoning = additional_kwargs.get("reasoning_content")
    return str(reasoning).strip() if reasoning else None


def to_thinking_blocks(msg: BaseMessage) -> list[ThinkingBlock] | None:
    """Extract structured thinking blocks from a BaseMessage."""
    from app.core.engine.message.schemas import ThinkingBlock
    reasoning = extract_reasoning_from_message(msg)
    if reasoning:
        return [ThinkingBlock(type="reasoning", content=reasoning)]
    return None


# ---------------------------------------------------------------------------
# 3. Thinking block construction (for MessageBlock / SSE / Mobile)
# ---------------------------------------------------------------------------


def build_thinking_blocks(thinking_content: str | None) -> list | None:
    """
    将推理字符串转换为结构化 ThinkingBlock 列表。
    """
    if not thinking_content:
        return None

    from app.core.engine.message.schemas import ThinkingBlock
    return [ThinkingBlock(type="reasoning", content=thinking_content)]


def infer_thinking_type(metadata: dict | None) -> str | None:
    """Infer thinking type from message metadata. Returns 'reasoning' if metadata contains reasoning_content."""
    if metadata and metadata.get("reasoning_content"):
        return "reasoning"
    return None


# ---------------------------------------------------------------------------
# 4. DB Serialization / Deserialization
# ---------------------------------------------------------------------------


def parse_thinking(raw: str | None) -> list[ThinkingBlock] | None:
    """Parse JSON-serialized thinking from DB string into structured list[ThinkingBlock]."""
    from app.core.engine.message.schemas import ThinkingBlock
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [ThinkingBlock.model_validate(item) for item in parsed]
    except (json.JSONDecodeError, ValueError):
        pass
    return None
def extract_tool_calls(msg: Any) -> list[dict]:
    """
    归一化从消息中提取工具调用。
    支持 LangChain BaseMessage 对象、AIMessageChunk 以及字典格式。
    """
    if hasattr(msg, "tool_calls"):
        return msg.tool_calls
    if isinstance(msg, dict):
        return msg.get("tool_calls", [])
    return []


def serialize_thinking(thinking: list[ThinkingBlock] | None) -> str | None:
    """Serialize structured thinking list into JSON string for DB storage."""
    if not thinking:
        return None
    return json.dumps([t.model_dump() for t in thinking], ensure_ascii=False)


def wrap_reasoning_for_db(reasoning: str | None) -> str | None:
    """Wrap raw reasoning_content string as structured JSON list for DB storage."""
    from app.core.engine.message.schemas import ThinkingBlock
    if not reasoning:
        return None
    return serialize_thinking([ThinkingBlock(type="reasoning", content=reasoning)])
