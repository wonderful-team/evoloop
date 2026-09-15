import logging
from collections.abc import AsyncGenerator
from typing import Any

import anthropic

from app.core.engine.message.native_classes import AIMessageChunk

logger = logging.getLogger(__name__)


def _apply_prompt_cache_breakpoint(messages: list[dict]) -> None:
    """在最后一条含文本的 user 消息末尾加 ephemeral 缓存断点（Anthropic 协议）。

    与网关层 OpenAI→Anthropic 转换的断点策略保持一致：system 断点由
    _format_system_content 负责；此处负责 messages 尾部断点，使历史前缀
    在直连模式（不经网关）下同样享受 prompt caching。tool_result 块
    不允许携带 cache_control，无文本块时向前回退查找更早的 user 消息。
    """
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") != "user":
            continue
        content = messages[i].get("content")
        if isinstance(content, list):
            for block in reversed(content):
                if isinstance(block, dict) and block.get("type") == "text":
                    block["cache_control"] = {"type": "ephemeral"}
                    return
        elif isinstance(content, str):
            messages[i]["content"] = [
                {
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
            return


class CompatibleChatAnthropic:
    """
    A robust, native, SDK-free ChatAnthropic wrapper that connects directly to the Anthropic Messages API.
    """

    provider = "anthropic"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        temperature: float = 0.3,
        streaming: bool = True,
        model_kwargs: dict | None = None,
        http_async_client: Any = None,
        **kwargs: Any,
    ):
        self.model = model_name
        self.temperature = temperature
        self.streaming = streaming
        self.model_kwargs = model_kwargs or {}
        self._tools = []

        # Anthropic SDK automatically appends /v1/messages, strip it if redundant
        normalized_url = base_url.rstrip("/")
        if normalized_url.endswith("/v1"):
            normalized_url = normalized_url[:-3]

        self.client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=normalized_url,
            http_client=http_async_client
        )

    def bind_tools(self, tools: list[Any]) -> "CompatibleChatAnthropic":
        self._tools = []
        for t in tools:
            # 优先使用工具自带的原始 JSON Schema（保留嵌套/enum/oneOf 结构），
            # 并按 Anthropic input_schema 约束清洗（内联 $ref、去 $defs/default）。
            raw_schema = getattr(t, "raw_args_schema", None)
            if isinstance(raw_schema, dict):
                from app.core.tools.schema_utils import clean_tool_schema_for_anthropic
                input_schema = clean_tool_schema_for_anthropic(raw_schema)
            else:
                input_schema = t.args_schema.model_json_schema() if getattr(t, "args_schema", None) else {"type": "object", "properties": {}}

            t_schema = {
                "name": t.name,
                "description": t.description or "",
                "input_schema": input_schema,
            }
            if "input_schema" in t_schema:
                params = t_schema["input_schema"]
                params.pop("title", None)
                params.pop("additionalProperties", None)
                if "$defs" in params:
                    params.pop("$defs", None)
            self._tools.append(t_schema)
        return self

    @staticmethod
    def _format_system_content(content: Any) -> Any:
        """Wrap plain-text system prompts in content blocks with prompt caching.

        Anthropic 的 system 参数支持 content-block 列表，可附带 cache_control
        实现 prompt caching。引擎层只构造普通字符串 SystemMessage，此处由
        adapter 负责 provider 专属格式；已显式构造为 block 列表时原样透传。
        """
        if isinstance(content, str):
            return [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]
        return content

    async def astream(self, messages: list[Any], config: dict = None, **kwargs: Any) -> AsyncGenerator[AIMessageChunk, None]:
        from app.core.engine.callbacks.bridge import (
            _get_callbacks,
            _get_metadata,
            _get_run_id,
            emit_llm_end,
            emit_llm_new_token,
            emit_llm_start,
        )
        from app.core.engine.message.native_classes import AIMessage

        callbacks = _get_callbacks(config)
        run_id = _get_run_id(config)
        metadata = _get_metadata(config)

        # Accept a bare prompt string (LangChain convention: a string prompt is
        # a single human/user message). Iterating a str directly yields one
        # character per step, which breaks the message loop below.
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        system_content = None
        api_messages = []

        # Convert native messages to Anthropic Messages structure
        for m in messages:
            role = m.get("role") if isinstance(m, dict) else m.type
            content = m.get("content") if isinstance(m, dict) else m.content

            if role == "system":
                system_content = self._format_system_content(content)
                continue

            if role in ("user", "human"):
                api_messages.append({"role": "user", "content": content})
            elif role in ("assistant", "ai"):
                tool_calls = m.get("tool_calls") if isinstance(m, dict) else m.tool_calls
                if tool_calls:
                    content_blocks = []
                    if content:
                        content_blocks.append({"type": "text", "text": content})
                    for tc in tool_calls:
                        tc_id = tc.get("id") or tc.get("tool_call_id")
                        tc_name = tc.get("name")
                        tc_args = tc.get("args")
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc_id or "",
                            "name": tc_name or "",
                            "input": tc_args or {},
                        })
                    api_messages.append({"role": "assistant", "content": content_blocks})
                else:
                    api_messages.append({"role": "assistant", "content": content})
            elif role == "tool":
                tool_call_id = m.get("tool_call_id") if isinstance(m, dict) else m.tool_call_id
                api_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_call_id,
                            "content": content
                        }
                    ]
                })

        if callbacks:
            await emit_llm_start(callbacks, run_id, metadata)

        _apply_prompt_cache_breakpoint(api_messages)

        req_params = {
            "model": self.model,
            "messages": api_messages,
            "temperature": self.temperature,
            **self.model_kwargs,
        }
        if system_content:
            req_params["system"] = system_content
        if self._tools:
            req_params["tools"] = self._tools

        accumulated: AIMessageChunk | None = None
        async with self.client.messages.stream(**req_params) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        tc = {
                            "index": event.index,
                            "id": block.id,
                            "name": block.name,
                            "args": "",
                        }
                        msg_chunk = AIMessageChunk(content="", tool_calls=[tc])
                    else:
                        continue
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        msg_chunk = AIMessageChunk(content=delta.text)
                    elif delta.type == "input_delta":
                        tc = {
                            "index": event.index,
                            "args": delta.partial_json
                        }
                        msg_chunk = AIMessageChunk(content="", tool_calls=[tc])
                    else:
                        continue
                else:
                    continue

                if callbacks:
                    await emit_llm_new_token(callbacks, msg_chunk.content, msg_chunk, run_id)

                if accumulated is None:
                    accumulated = msg_chunk
                else:
                    accumulated = accumulated + msg_chunk

                yield msg_chunk

        if callbacks and accumulated is not None:
            final_msg = AIMessage(
                content=accumulated.content,
                tool_calls=accumulated.tool_calls,
                additional_kwargs=dict(accumulated.additional_kwargs),
            )
            await emit_llm_end(callbacks, final_msg, run_id)

    async def ainvoke(self, messages: list[Any], config: dict = None, **kwargs: Any) -> Any:
        """Native non-streaming ainvoke wrapper that accumulates astream."""
        from app.core.engine.message.native_classes import AIMessage

        response_content = ""
        tool_calls = []
        additional_kwargs = {}

        async for chunk in self.astream(messages, config=config, **kwargs):
            if chunk.content:
                response_content += chunk.content
            if chunk.tool_calls:
                tool_calls.extend(chunk.tool_calls)
            if chunk.additional_kwargs:
                additional_kwargs.update(chunk.additional_kwargs)

        return AIMessage(
            content=response_content,
            tool_calls=tool_calls,
            additional_kwargs=additional_kwargs,
        )

    def with_structured_output(self, output_schema: type, method: str = "function_calling"):
        """
        Bind a Pydantic schema for structured output via function calling.
        Returns a wrapper whose ainvoke() yields a parsed instance of output_schema.
        """
        from app.infrastructure.llm.adaptive import _StructuredOutputWrapper

        return _StructuredOutputWrapper(self, output_schema, method=method)
