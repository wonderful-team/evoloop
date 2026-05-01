"""
Shared message utilities for agent nodes.

Contains common functions for message processing, history repair, and extraction.

This module re-exports functions from specialized sub-modules for backward
compatibility. New code should import directly from the specialized modules.
"""

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage, HumanMessage

from app.utils.token import estimate_tokens

logger = logging.getLogger(__name__)


# Mapping of tool-specific argument aliases for consistent i18n rendering
# format: {tool_name: {old_key: new_key}}
TOOL_ARG_ALIASES = {
    "search_files": {"pattern": "query"},
    "search_code": {"pattern": "query"},
    "search_web": {"pattern": "query"},
    "list_directory": {"path": "path"},  # Ensure path is always available
    "read_file": {"path": "path"},
}


def to_base_message(msg: Any) -> BaseMessage | None:
    """
    Convert a database Message record or similar object to a LangChain BaseMessage.

    Args:
        msg: Object with role, content, and optionally tool_calls / tool_call_id

    Returns:
        A LangChain message object or None if role is unknown
    """
    role = getattr(msg, "role", None)
    # Defensive: content may be None in DB; LangChain v2 rejects None content
    content = getattr(msg, "content", "") or ""

    # Preserve key metadata that fold_messages and other utilities need
    msg_id = str(getattr(msg, "id", "")) or None
    created_at = getattr(msg, "created_at", None)
    thinking_raw = getattr(msg, "thinking", None)

    # Build additional_kwargs explicitly for clarity and version safety
    additional_kwargs: dict[str, Any] = {}
    if created_at:
        additional_kwargs["created_at"] = created_at
    if thinking_raw:
        additional_kwargs["thinking"] = thinking_raw
    
    # Preserve status for folder/mapping logic
    status = getattr(msg, "status", None)
    if status:
        additional_kwargs["status"] = status

    try:
        if role == "human":
            return HumanMessage(content=content, id=msg_id, additional_kwargs=additional_kwargs)
        elif role == "ai":
            tool_calls = normalize_tool_calls(getattr(msg, "tool_calls", []))

            return AIMessage(
                content=content,
                id=msg_id,
                tool_calls=tool_calls,
                additional_kwargs=additional_kwargs
            )
        elif role == "tool":
            # For database records, name might be stored in 'tool_name' or derived from tool_calls
            return ToolMessage(
                content=content,
                id=msg_id,
                tool_call_id=getattr(msg, "tool_call_id", "") or "",
                name=getattr(msg, "tool_name", None),
                additional_kwargs=additional_kwargs
            )
        elif role == "system":
            return SystemMessage(content=content, id=msg_id, additional_kwargs=additional_kwargs)
    except Exception as e:
        logger.warning(f"[to_base_message] Failed to convert msg id={msg_id} role={role}: {e}")
        return None

    return None


def normalize_tool_call(tc: Any) -> dict[str, Any]:
    """
    Standardize tool call structure to LangChain format:
    {"id": "...", "name": "...", "args": {...}}

    Handles:
    - LangChain normalized dicts
    - OpenAI raw tool call dicts (with 'function' and 'arguments' string)
    - Pydantic models (with .model_dump())
    """
    if not isinstance(tc, dict):
        if hasattr(tc, "model_dump"):
            tc = tc.model_dump()
        else:
            return {}

    # 1. Check for standard LangChain format
    res_id = tc.get("id") or tc.get("tool_call_id") or ""
    res_name = tc.get("name") or tc.get("tool_name") or ""
    res_args = tc.get("args") or {}

    # 2. Handle OpenAI legacy format: {"function": {"name": "...", "arguments": "{...}"}}
    if not res_name or not res_args:
        fn_info = tc.get("function")
        if isinstance(fn_info, dict):
            if not res_name:
                res_name = fn_info.get("name") or ""
            if not res_args:
                args_raw = fn_info.get("arguments")
                if isinstance(args_raw, str):
                    try:
                        res_args = json.loads(args_raw)
                    except (json.JSONDecodeError, ValueError):
                        res_args = {}
                elif isinstance(args_raw, dict):
                    res_args = args_raw

    # 3. Apply Aliases for i18n consistency
    if res_name in TOOL_ARG_ALIASES:
        aliases = TOOL_ARG_ALIASES[res_name]
        for old_k, new_k in aliases.items():
            if old_k in res_args and new_k not in res_args:
                res_args[new_k] = res_args[old_k]

    return {
        "id": res_id,
        "name": res_name,
        "args": res_args,
    }


def normalize_tool_calls(tool_calls: Any) -> list[dict[str, Any]]:
    """Normalize a list of tool calls."""
    if not tool_calls:
        return []

    if isinstance(tool_calls, str):
        try:
            tool_calls = json.loads(tool_calls)
        except (json.JSONDecodeError, ValueError):
            return []

    if not isinstance(tool_calls, list):
        return []

    return [normalize_tool_call(tc) for tc in tool_calls]


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
    if isinstance(msg, AIMessage) and msg.tool_calls:
        overhead += 8  # tool_calls have extra overhead
    return base + overhead


def count_total_tokens(messages: list[BaseMessage]) -> int:
    """Sum estimated tokens for all messages (fast path, no model required)."""
    return sum(estimate_message_tokens(m) for m in messages)
