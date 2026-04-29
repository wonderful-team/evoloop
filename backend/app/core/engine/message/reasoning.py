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
from typing import Any, Mapping, Type, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.core.engine.message.schemas import ThinkingBlock

from langchain_core.messages import BaseMessage, AIMessage, AIMessageChunk
from langchain_openai import ChatOpenAI
from app.infrastructure.llm.adaptive import AdaptiveChatOpenAI

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
                # Put into additional_kwargs so LangChain can carry it forward
                result.additional_kwargs["reasoning_content"] = (
                    result.additional_kwargs.get("reasoning_content", "") + reasoning
                )
            return result

        base_module._convert_delta_to_message_chunk = _convert_delta_with_reasoning

        # Patch 2: Sending (Message -> Dict)
        def _get_payload_with_reasoning_factory(original_func: Any):
            def _get_payload_with_reasoning(self: Any, input_: Any, **kwargs: Any) -> dict:
                # 1. Convert via original logic
                payload = original_func(self, input_, **kwargs)
                logger.info(f"[Reasoning] _get_request_payload CALLED for model {getattr(self, 'model_name', 'unknown')}")
                
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
                                    logger.info(f"[Reasoning] Injected reasoning_content ({len(str(reasoning))} chars) for message index {i}")
                                elif msg_dict.get("role") == "assistant" and ("tool_calls" in msg_dict or "function_call" in msg_dict):
                                    if "reasoning_content" not in msg_dict:
                                        msg_dict["reasoning_content"] = ""
                                        logger.info(f"[Reasoning] Injected EMPTY reasoning_content for message index {i} (tool call safety)")
                        else:
                            logger.debug(f"[Reasoning] Message count mismatch: payload={len(payload_msgs)}, source={len(messages)}")
                except Exception as e:
                    logger.debug(f"[Reasoning] Payload injection failed: {e}")
                
                return payload
            return _get_payload_with_reasoning

        # Apply to both base and adaptive classes
        ChatOpenAI._get_request_payload = _get_payload_with_reasoning_factory(ChatOpenAI._get_request_payload)
        AdaptiveChatOpenAI._get_request_payload = _get_payload_with_reasoning_factory(AdaptiveChatOpenAI._get_request_payload)

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
                            has_reasoning = "reasoning_content" in msg
                            
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
                                # print(f"DEBUG: [Reasoning] -> FORCED reasoning_content at index {i}")
                            else:
                                if "reasoning_content" in msg:
                                    msg.pop("reasoning_content")
                                    modified = True
                                    # print(f"DEBUG: [Reasoning] -> STRIPPED reasoning_content from {role} at {i}")
                        
                        if modified:
                            # Re-encode body
                            new_content = json.dumps(body).encode("utf-8")
                            request._content = new_content
                            request.stream = httpx.ByteStream(new_content)
                            request.headers["Content-Length"] = str(len(new_content))
                            if "Transfer-Encoding" in request.headers:
                                del request.headers["Transfer-Encoding"]
                except Exception as e:
                    pass # Silent failure in production
            
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
