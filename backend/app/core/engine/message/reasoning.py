"""
Reasoning content — single source of truth for thinking data.

This module provides:
1. Monkey-patch for langchain-openai to capture reasoning_content from streaming deltas
2. Extraction from LangChain messages / additional_kwargs

Import order constraint:
    The monkey-patch must be applied BEFORE any ChatOpenAI instances are created.
    LLM factory imports this module at startup to ensure the patch is active.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping, Type

import httpx
from langchain_core.messages import BaseMessage, AIMessage, AIMessageChunk
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. Monkey-patch (must run before any ChatOpenAI instantiation)
# ---------------------------------------------------------------------------


def _apply_reasoning_patch() -> None:
    """Apply monkey-patch to langchain_openai for reasoning_content support."""
    try:
        import langchain_openai.chat_models.base as base_module

        # Patch 1: Receiving (Delta -> MessageChunk)
        # Capture original _convert_delta_to_message_chunk
        _original_delta_convert = base_module._convert_delta_to_message_chunk

        def _convert_delta_with_reasoning(_dict: Mapping, default_class: Type) -> AIMessageChunk:
            # 1. Convert via original logic
            result = _original_delta_convert(_dict, default_class)

            # 2. Extract Reasoning (Kimi/DeepSeek format)
            reasoning = _dict.get("reasoning_content")
            if reasoning and isinstance(result, AIMessageChunk):
                existing = result.additional_kwargs.get("reasoning_content", "")
                new_reasoning = existing + reasoning
                # Keep raw string for LLM payload injection (monkey-patch round-trip)
                result.additional_kwargs["reasoning_content"] = new_reasoning
                # Sync unified key for downstream consumption
                result.additional_kwargs["thinking"] = new_reasoning
            return result

        base_module._convert_delta_to_message_chunk = _convert_delta_with_reasoning

        # Patch 2: Sending (Message -> Dict)
        def _get_payload_with_reasoning_factory(original_func: Any):
            def _get_payload_with_reasoning(self: Any, input_: Any, **kwargs: Any) -> dict:
                # 1. Convert via original logic
                payload = original_func(self, input_, **kwargs)

                # 2. Inject Reasoning from messages back to the final payload
                try:
                    if isinstance(input_, list) and all(isinstance(m, BaseMessage) for m in input_):
                        messages = input_
                    else:
                        messages = self._convert_input(input_).to_messages()

                    if "messages" in payload:
                        payload_msgs = payload["messages"]
                        if len(payload_msgs) == len(messages):
                            for i, (msg, msg_dict) in enumerate(zip(messages, payload_msgs)):
                                if isinstance(msg, AIMessage) and "reasoning_content" in msg.additional_kwargs:
                                    reasoning = msg.additional_kwargs["reasoning_content"]
                                    msg_dict["reasoning_content"] = reasoning
                                elif msg_dict.get("role") == "assistant" and ("tool_calls" in msg_dict or "function_call" in msg_dict):
                                    if "reasoning_content" not in msg_dict:
                                        msg_dict["reasoning_content"] = ""
                except Exception as e:
                    logger.debug(f"[Reasoning] Payload injection failed: {e}")

                return payload
            return _get_payload_with_reasoning

        # Apply to base class (AdaptiveChatOpenAI will inherit this)
        ChatOpenAI._get_request_payload = _get_payload_with_reasoning_factory(ChatOpenAI._get_request_payload)

        # Patch 3: Final fallback - intercept httpx.AsyncClient.send
        _original_httpx_send = httpx.AsyncClient.send

        async def _patched_httpx_send(self: Any, request: httpx.Request, **kwargs: Any) -> httpx.Response:
            # Check if this is a chat completion request
            url_str = str(request.url)
            if request.method == "POST" and ("/chat/completions" in url_str or "/messages" in url_str):
                try:
                    # Read and patch the body
                    content = request.read()
                    body = json.loads(content)

                    if "messages" in body:
                        modified = False
                        for i, msg in enumerate(body["messages"]):
                            role = msg.get("role")

                            if role == "assistant":
                                # Always ensure reasoning_content exists and is at the front
                                val = msg.get("reasoning_content")

                                # Kimi considers "" as missing, especially for tool call messages.
                                # We inject a single space as a placeholder to satisfy the "non-empty" requirement.
                                if not val:
                                    val = " "

                                # Reconstruct to ensure ordering (role first, then reasoning)
                                # This is critical for Kimi compliance in multi-turn history
                                new_msg = {"role": "assistant", "reasoning_content": val}
                                for k, v in msg.items():
                                    if k not in ["role", "reasoning_content"]:
                                        new_msg[k] = v

                                body["messages"][i] = new_msg
                                modified = True
                            else:
                                if "reasoning_content" in msg:
                                    msg.pop("reasoning_content")
                                    modified = True

                        if modified:
                            # Re-encode body
                            new_content = json.dumps(body).encode("utf-8")
                            request._content = new_content
                            request.stream = httpx.ByteStream(new_content)
                            request.headers["Content-Length"] = str(len(new_content))
                            if "Transfer-Encoding" in request.headers:
                                del request.headers["Transfer-Encoding"]
                except Exception:
                    pass  # Silent failure in production

            return await _original_httpx_send(self, request, **kwargs)

        httpx.AsyncClient.send = _patched_httpx_send

        logger.info("[Reasoning] Applied Kimi reasoning_content safety patches")

    except Exception as e:
        logger.warning(f"[Reasoning] Failed to apply patch: {e}")


# Auto-apply on module import
_apply_reasoning_patch()


# ---------------------------------------------------------------------------
# 2. Extraction
# ---------------------------------------------------------------------------


def extract_reasoning_from_message(message: BaseMessage) -> str | None:
    """从完整的 LangChain 消息中提取推理内容 (支持 Kimi/OpenAI 格式)"""
    return extract_reasoning_from_kwargs(message.additional_kwargs)


def extract_reasoning_from_kwargs(additional_kwargs: dict | None) -> str | None:
    """Extract raw reasoning content string from additional_kwargs dict.

    Priority:
        1. ``additional_kwargs["thinking"]`` (unified string set by DB load or delta sync)
        2. ``additional_kwargs["reasoning_content"]`` (raw string from monkey-patch)
    """
    if not additional_kwargs:
        return None

    # 1. Prefer unified "thinking" key (set by DB load or delta sync)
    thinking = additional_kwargs.get("thinking")
    if isinstance(thinking, str) and thinking.strip():
        return thinking.strip()

    # 2. Fallback to raw reasoning_content (legacy / streaming chunks)
    reasoning = additional_kwargs.get("reasoning_content")
    return str(reasoning).strip() if reasoning else None


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
