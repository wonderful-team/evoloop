"""
reasoning_patch.py — LangChain / httpx monkey-patches for reasoning_content support.

职责边界：
  - 此模块只做 SDK/HTTP 层的兼容补丁，不包含任何业务逻辑
  - 必须在任何 ChatOpenAI 实例创建之前 import（由 factory.py 保证）
  - 从 app.core.engine.message.reasoning 迁移至此，归属于正确的基础设施层
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

import httpx
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


def _apply_reasoning_patch() -> None:
    """Apply monkey-patch to langchain_openai for reasoning_content support."""
    try:
        import langchain_openai.chat_models.base as base_module

        # Patch 1: Receiving (Delta -> MessageChunk)
        # Capture original _convert_delta_to_message_chunk
        _original_delta_convert = base_module._convert_delta_to_message_chunk

        def _convert_delta_with_reasoning(_dict: Mapping, default_class: type) -> AIMessageChunk:
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

        # Patch 1.5: Receiving (Dict -> Message, non-streaming)
        _original_dict_convert = base_module._convert_dict_to_message

        def _convert_dict_with_reasoning(
            _dict: Mapping[str, Any], default_class: type = AIMessage  # type: ignore[assignment]
        ) -> BaseMessage:
            result = _original_dict_convert(_dict, default_class)
            if isinstance(result, AIMessage):
                reasoning = _dict.get("reasoning_content")
                if reasoning:
                    result.additional_kwargs["reasoning_content"] = reasoning
                    result.additional_kwargs["thinking"] = reasoning
            return result

        base_module._convert_dict_to_message = _convert_dict_with_reasoning

        # Patch 2: Sending (Message -> Dict)
        def _get_payload_with_reasoning_factory(original_func: Any):
            def _get_payload_with_reasoning(self: Any, input_: Any, **kwargs: Any) -> dict:
                # 1. Convert via original logic
                payload = original_func(self, input_, **kwargs)

                # Detect Kimi/Moonshot
                is_kimi = False
                base_url = getattr(self, "openai_api_base", "") or getattr(self, "base_url", "")
                if base_url:
                    base_url_str = str(base_url).lower()
                    is_kimi = "kimi" in base_url_str or "moonshot" in base_url_str

                model_name = getattr(self, "model_name", "") or getattr(self, "model", "")
                if model_name:
                    model_name_str = str(model_name).lower()
                    if "kimi" in model_name_str or "moonshot" in model_name_str:
                        is_kimi = True

                # 2. Inject Reasoning from messages back to the final payload (only for Kimi)
                if is_kimi:
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
        ChatOpenAI._get_request_payload = _get_payload_with_reasoning_factory(ChatOpenAI._get_request_payload)  # type: ignore[method-assign]

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

                    # Check if target is Kimi/Moonshot
                    is_kimi = "kimi" in url_str.lower() or "moonshot" in url_str.lower()

                    if "messages" in body:
                        modified = False
                        for i, msg in enumerate(body["messages"]):
                            role = msg.get("role")

                            if role == "assistant":
                                if is_kimi:
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
                                    # For non-Kimi models (like GLM, OpenAI), strip reasoning_content to avoid 400 Bad Request
                                    if "reasoning_content" in msg:
                                        msg.pop("reasoning_content")
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

        httpx.AsyncClient.send = _patched_httpx_send  # type: ignore[method-assign]

        logger.info("[Reasoning] Applied Kimi reasoning_content safety patches")

    except Exception as e:
        logger.warning(f"[Reasoning] Failed to apply patch: {e}")


# Auto-apply on module import
_apply_reasoning_patch()
