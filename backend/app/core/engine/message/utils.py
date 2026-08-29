"""
Shared message utilities for agent nodes.
"""

import logging
from typing import Any

from app.core.engine.message.native_classes import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from app.utils.extract import safe_parse_json, safe_parse_json_value
from app.utils.token import estimate_tokens

logger = logging.getLogger(__name__)


def parse_tool_input(input_str: str | None) -> dict:
    """
    Robustly parse tool input string into a dictionary.
    """
    if not input_str or not input_str.strip():
        return {}

    parsed = safe_parse_json(input_str)
    return parsed or {}


def _msg_field(msg, key, default=None):
    return msg.get(key) if isinstance(msg, dict) else getattr(msg, key, default)


def _coerce_args(raw: Any) -> dict:
    """Coerce a tool-call args value (str/dict/None) into a dict."""
    if isinstance(raw, str):
        return safe_parse_json(raw) or {}
    return raw or {}


def to_base_message(msg: Any) -> BaseMessage | None:
    if not msg:
        return None

    if isinstance(msg, dict):
        role = msg.get("role")
        content = msg.get("content", "") or ""
        msg_id = str(msg.get("id", "")) or None
        created_at = msg.get("created_at")
        thinking_raw = msg.get("thinking")
        status = msg.get("status")
        meta_data = msg.get("meta_data") or msg.get("metadata")
        node_source = msg.get("node_source")
        additional_kwargs = dict(msg.get("additional_kwargs", {}) or {})
    else:
        role = getattr(msg, "role", None)
        content = getattr(msg, "content", "") or ""
        msg_id = str(getattr(msg, "id", "")) or None
        created_at = getattr(msg, "created_at", None)
        thinking_raw = getattr(msg, "thinking", None)
        status = getattr(msg, "status", None)
        meta_data = getattr(msg, "meta_data", None) or getattr(msg, "metadata", None)
        node_source = getattr(msg, "node_source", None)
        additional_kwargs = dict(getattr(msg, "additional_kwargs", {}) or {})

    if created_at:
        additional_kwargs["created_at"] = created_at
    if thinking_raw:
        additional_kwargs["thinking"] = thinking_raw
    if status:
        additional_kwargs["status"] = status
    if meta_data:
        additional_kwargs["metadata"] = meta_data
    if node_source:
        additional_kwargs["node_source"] = node_source

    try:
        message = None
        if role == "human" or role == "user":
            message = HumanMessage(
                content=content,
                id=msg_id,
                additional_kwargs=additional_kwargs
            )
        elif role == "ai" or role == "assistant":
            tc_source = _msg_field(msg, "tool_calls", [])
            tool_calls = normalize_tool_calls(tc_source)
            message = AIMessage(
                content=content,
                id=msg_id,
                tool_calls=tool_calls,
                additional_kwargs=additional_kwargs,
            )
        elif role == "tool":
            message = ToolMessage(
                content=content,
                id=msg_id,
                tool_call_id=_msg_field(msg, "tool_call_id") or "",
                name=_msg_field(msg, "name") or _msg_field(msg, "tool_name"),
                additional_kwargs=additional_kwargs,
            )
        elif role == "system":
            message = SystemMessage(
                content=content,
                id=msg_id,
                additional_kwargs=additional_kwargs
            )

        if message:
            message.metadata = additional_kwargs
            is_err = additional_kwargs.get("status") == "error" or additional_kwargs.get("is_error") or False
            if is_err:
                message.metadata["is_error"] = True
            return message
    except (ValueError, TypeError, AttributeError) as e:
        logger.warning(f"[to_base_message] Failed to convert msg role={role}: {e}", exc_info=True)
        return None

    return None


def normalize_tool_call(tc: Any) -> dict[str, Any]:
    """
    Standardize tool call structure to:
    {"id": "...", "name": "...", "args": {...}}
    """
    if isinstance(tc, dict):
        res_id = tc.get("id") or tc.get("tool_call_id") or ""
        res_name = tc.get("name") or tc.get("tool_name") or ""
        res_args = tc.get("args") or {}
        if not res_name or not res_args:
            fn_info = tc.get("function")
            if isinstance(fn_info, dict):
                if not res_name:
                    res_name = fn_info.get("name") or ""
                if not res_args:
                    args_raw = fn_info.get("arguments")
                    if isinstance(args_raw, str) or isinstance(args_raw, dict):
                        res_args = _coerce_args(args_raw)
            elif fn_info is not None:
                if not res_name:
                    res_name = getattr(fn_info, "name", "") or ""
                if not res_args:
                    args_raw = getattr(fn_info, "arguments", "")
                    if isinstance(args_raw, str) or isinstance(args_raw, dict):
                        res_args = _coerce_args(args_raw)
    else:
        res_id = getattr(tc, "id", None) or getattr(tc, "tool_call_id", None) or ""
        res_name = getattr(tc, "name", None) or getattr(tc, "tool_name", None) or ""
        res_args = getattr(tc, "args", None) or {}
        if not res_name or not res_args:
            fn_info = getattr(tc, "function", None)
            if isinstance(fn_info, dict):
                if not res_name:
                    res_name = fn_info.get("name") or ""
                if not res_args:
                    args_raw = fn_info.get("arguments")
                    if isinstance(args_raw, str) or isinstance(args_raw, dict):
                        res_args = _coerce_args(args_raw)
            elif fn_info is not None:
                if not res_name:
                    res_name = getattr(fn_info, "name", "") or ""
                if not res_args:
                    args_raw = getattr(fn_info, "arguments", "")
                    if isinstance(args_raw, str) or isinstance(args_raw, dict):
                        res_args = _coerce_args(args_raw)

    if isinstance(res_args, str):
        res_args = _coerce_args(res_args)

    result = {"id": res_id, "name": res_name, "args": res_args}

    if isinstance(tc, dict):
        if "type" in tc:
            result["type"] = tc["type"]
        if "index" in tc:
            result["index"] = tc["index"]
    else:
        if hasattr(tc, "type"):
            result["type"] = tc.type
        if hasattr(tc, "index"):
            result["index"] = tc.index

    return result


def normalize_tool_calls(tool_calls: Any) -> list[dict[str, Any]]:
    """Normalize a list of tool calls."""
    if not tool_calls:
        return []

    if isinstance(tool_calls, str):
        parsed = safe_parse_json_value(tool_calls)
        if not isinstance(parsed, list):
            return []
        tool_calls = parsed

    if not isinstance(tool_calls, list):
        return []

    return [normalize_tool_call(tc) for tc in tool_calls]


def get_message_text(message: Any) -> str:
    """
    Robustly extract text content from message dict, object or string.
    """
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        content = message.get("content", "")
    elif hasattr(message, "content"):
        content = message.content
    else:
        content = ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, str):
                text_parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
        return "\n".join(text_parts)

    return ""


def estimate_message_tokens(msg: Any) -> int:
    """
    Estimate token count for a single message.
    """
    text = get_message_text(msg)
    base = estimate_tokens(text)
    overhead = 4

    if isinstance(msg, dict):
        role = msg.get("role")
        tool_calls = msg.get("tool_calls")
    else:
        role = getattr(msg, "type", "user")
        tool_calls = getattr(msg, "tool_calls", None)

    if role in ("assistant", "ai") and tool_calls:
        overhead += 8
    return base + overhead


def count_total_tokens(messages: list) -> int:
    """Sum estimated tokens for all messages."""
    return sum(estimate_message_tokens(m) for m in messages)
