"""
InferenceEngine - Pure LLM execution logic.
"""

import hashlib
import logging
import time
from collections.abc import Callable
from typing import Any

from app.core.engine.context_trimmer import ContextTrimmer, TrimTrigger
from app.core.engine.error_handler import LLM_EXCEPTIONS, LLMErrorHandler, with_llm_retry
from app.core.exceptions import InferenceError
from app.core.engine.message.converter import EvoMessageConverter
from app.core.engine.message.native_classes import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from app.core.engine.message.reasoning import extract_reasoning_from_message
from app.infrastructure.llm.factory import LLMFactory

logger = logging.getLogger(__name__)


def _dicts_to_messages(messages: list[dict]) -> list[BaseMessage]:
    """Helper to convert standard dict messages to native BaseMessage for LLM compatibility."""
    lc_messages = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        additional_kwargs = m.get("additional_kwargs") or {}
        
        if role == "system":
            lc_messages.append(SystemMessage(content=content, additional_kwargs=additional_kwargs))
        elif role == "user":
            lc_messages.append(HumanMessage(content=content, name=m.get("name"), additional_kwargs=additional_kwargs))
        elif role == "assistant":
            tool_calls = m.get("tool_calls") or []
            # Normalize tool calls to standard structure: [{'name': '...', 'args': {...}, 'id': '...'}]
            lc_tool_calls = []
            for tc in tool_calls:
                lc_tool_calls.append({
                    "name": tc.get("name") or "",
                    "args": tc.get("args") or {},
                    "id": tc.get("id") or tc.get("tool_call_id") or "",
                })
            lc_messages.append(AIMessage(content=content, tool_calls=lc_tool_calls, additional_kwargs=additional_kwargs))
        elif role == "tool":
            lc_messages.append(ToolMessage(
                content=content,
                tool_call_id=m.get("tool_call_id") or "",
                name=m.get("name"),
                additional_kwargs=additional_kwargs
            ))
        else:
            lc_messages.append(HumanMessage(content=content, additional_kwargs=additional_kwargs))
    return lc_messages


def _message_to_dict(msg: BaseMessage) -> dict:
    """Helper to convert native BaseMessage back to standard dict."""
    from app.core.engine.message.utils import normalize_tool_calls

    res = {
        "role": "assistant" if isinstance(msg, AIMessage) else ("user" if isinstance(msg, HumanMessage) else ("system" if isinstance(msg, SystemMessage) else "tool")),
        "content": msg.content,
        "additional_kwargs": dict(msg.additional_kwargs or {}),
    }
    if isinstance(msg, AIMessage):
        res["tool_calls"] = normalize_tool_calls(msg.tool_calls)
    elif isinstance(msg, ToolMessage):
        res["tool_call_id"] = msg.tool_call_id
        res["name"] = msg.name
    return res


class InferenceEngine:
    """Instance-based inference engine for LLM ReAct loops."""

    def __init__(
        self,
        llm_factory: Any | None = None,
        context_trimmer: ContextTrimmer | None = None,
    ):
        self._llm_factory = llm_factory or LLMFactory
        self._context_trimmer = context_trimmer or ContextTrimmer()

    async def create_llm(self, model: str | None, temperature: float, streaming: bool = True):
        llm = await self._llm_factory.create_llm(model_name=model, temperature=temperature, streaming=streaming)
        provider = self._detect_provider(llm)
        return llm, provider

    def _detect_provider(self, llm) -> str:
        class_name = llm.__class__.__name__
        if "Anthropic" in class_name:
            return "anthropic"
        return "openai"

    def bind_tools(self, llm, tools: list[Any]):
        if tools:
            return llm.bind_tools(tools), {t.name: t for t in tools}
        return llm, {}

    @staticmethod
    @with_llm_retry(max_attempts=3)
    async def _stream_llm_response(llm_with_tools, loop_messages, config):
        response = None
        # Construct config with callbacks mapped properly
        lc_config = {
            "callbacks": config.get("callbacks"),
            "configurable": config.get("configurable"),
            "metadata": config.get("metadata"),
        }
        async for chunk in llm_with_tools.astream(loop_messages, config=lc_config):
            if response is None:
                response = chunk
            else:
                response = response + chunk

        if response is None:
            raise InferenceError(
                error_type="empty_response",
                user_friendly_msg="LLM returned an empty response (no chunks received).",
                raw_error="Empty stream from LLM provider",
            )

        if isinstance(response, AIMessageChunk):
            response = AIMessage(
                content=response.content,
                additional_kwargs=response.additional_kwargs,
                tool_calls=response.tool_calls,
                response_metadata=response.response_metadata,
            )

        return response

    def build_system_messages(
        self, system_prompt: str, provider: str
    ) -> list[dict]:
        """Build provider-optimized system messages."""
        if provider == "anthropic":
            return [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ]
                }
            ]
        return [{"role": "system", "content": system_prompt}]

    async def _prepare_turn_context(
        self,
        loop_messages: list[dict],
        model: str | None,
        name: str,
        thread_id: str | None,
        run_id: str | None,
        config: dict,
    ) -> tuple[list[dict], dict[str, Any] | None]:
        if model:
            trim_result = self._context_trimmer.trim(
                messages=loop_messages,
                model=model,
                node_source=name.lower(),
                stages={"window", "repair"},
            )
            if trim_result.trigger != TrimTrigger.NONE:
                from app.core.engine.hooks import HookContext, HookEvent, hook_system

                # Map messages to native BaseMessage list for hook
                await hook_system.trigger(
                    HookEvent.PRE_COMPACT,
                    HookContext(
                        thread_id=thread_id,
                        run_id=run_id,
                        messages=_dicts_to_messages(loop_messages),
                        project_id=config.get("configurable", {}).get("project_id"),
                        member_id=config.get("configurable", {}).get("member_id"),
                        compact_trigger=trim_result.trigger.name.lower(),
                    ),
                )

                loop_messages = trim_result.messages
                logger.info(
                    f"[{name}] Loop trim: {trim_result.before_count} -> {trim_result.after_count} msgs"
                )

            if loop_messages:
                # Find last user message
                for i in range(len(loop_messages) - 1, -1, -1):
                    if loop_messages[i].get("role") == "user":
                        from app.core.engine.context_monitor import ContextMonitor

                        # Compute stats via ContextMonitor (expects list of dicts)
                        dashboard = (
                            "\n\n"
                            + ContextMonitor.calculate(
                                _dicts_to_messages(loop_messages), model=model
                            ).to_prompt()
                        )

                        original_content = loop_messages[i].get("content", "")
                        if isinstance(original_content, str):
                            new_content = original_content + dashboard
                        elif isinstance(original_content, list):
                            new_content = list(original_content) + [
                                {"type": "text", "text": dashboard.strip()}
                            ]
                        else:
                            break

                        # Copy message dict to avoid mutating history directly
                        loop_messages[i] = {
                            **loop_messages[i],
                            "content": new_content,
                        }
                        break

        msg_count = len(loop_messages)
        if model:
            from app.core.engine.context_monitor import ContextMonitor
            stats = ContextMonitor.calculate(_dicts_to_messages(loop_messages), model=model)
            logger.info(
                f"--- {name} Context: {msg_count} msgs, ~{stats.total_tokens} tokens ({stats.usage_ratio * 100:.1f}%) ---"
            )
        else:
            logger.info(f"--- {name} Context: {msg_count} msgs ---")

        return loop_messages, None

    @staticmethod
    def _format_llm_endpoint(llm) -> str:
        raw = getattr(llm, "bound", llm)
        base_url = getattr(raw, "openai_api_base", None)
        model = getattr(raw, "model", None) or getattr(raw, "model_name", None) or "?"
        if base_url:
            return f"POST {base_url}/chat/completions  model={model}"
        client_params = getattr(raw, "_client_params", None) or {}
        base_url = client_params.get("base_url") or getattr(raw, "base_url", "")
        if base_url:
            return f"POST {base_url}/v1/messages  model={model}"
        return f"model={model}"

    async def _execute_llm_call(
        self,
        llm_with_tools,
        loop_messages: list[dict],
        config: dict,
        name: str,
        system_prompt: str,
        history_messages: list[dict],
        turn_id: int,
        on_thinking: Callable | None = None,
        max_steps: int | None = None,
        is_single_shot: bool = False,
        sys_hash: str | None = None,
    ) -> dict:
        endpoint = self._format_llm_endpoint(llm_with_tools)
        logger.info(f"[{name}] ▶️ LLM call (turn={turn_id}) {endpoint}")
        
        # Convert loop messages to native BaseMessage format for LLM invocation
        lc_loop_messages = _dicts_to_messages(loop_messages)
        
        try:
            start_perf = time.perf_counter()
            response = await self._stream_llm_response(llm_with_tools, lc_loop_messages, config)
            latency = time.perf_counter() - start_perf
            logger.info(f"[{name}] LLM Latency: {latency:.2f}s")
        except LLM_EXCEPTIONS as e:
            LLMErrorHandler.raise_inference_error(e)

        run_id = config.get("configurable", {}).get("run_id")
        if run_id:
            response.additional_kwargs["run_id"] = run_id

        handler = config.get("configurable", {}).get("message_handler")
        if handler and handler.last_persisted_message_id:
            response.id = handler.last_persisted_message_id
            response.additional_kwargs["sequence_number"] = (
                handler.last_persisted_sequence
            )

        thinking_content = extract_reasoning_from_message(response)
        if thinking_content:
            logger.info(f"[{name}] Thinking: {thinking_content[:200]}...")
            if on_thinking:
                await on_thinking(thinking_content)

        return _message_to_dict(response)

    async def _process_tool_executions(
        self,
        response: dict,
        name: str,
        config: dict,
        interceptors: dict[str, Callable] | None,
        tool_executor: Any | None,
        local_tool_history: list,
    ) -> tuple[list[dict], Any | None, list[Any]]:
        pending_signal = None
        queued_signals: list[Any] = []
        remaining_tool_calls = []

        if isinstance(response, dict):
            tool_calls = response.get("tool_calls") or []
        else:
            tool_calls = getattr(response, "tool_calls", None) or []
        for tc in tool_calls:
            interceptor = (interceptors or {}).get(tc["name"])
            if interceptor:
                sig = await interceptor(tc, config)
                if sig is not None:
                    if pending_signal is None:
                        pending_signal = sig
                    else:
                        logger.info(f"[{name}] Queuing additional signal: {tc['name']}")
                        queued_signals.append(sig)
                    continue

            remaining_tool_calls.append(tc)

        tool_results = []
        if remaining_tool_calls and tool_executor is not None:
            logger.info(
                f"[{name}] 🛠   Executing {len(remaining_tool_calls)} tool calls"
            )
            res, batch_signal = await tool_executor.execute_batch(
                remaining_tool_calls, local_tool_history
            )
            tool_results = res

            if batch_signal and pending_signal is None:
                logger.info(
                    f"[{name}] Post-execution signal detected: {type(batch_signal).__name__}"
                )
                pending_signal = batch_signal

            logger.info(f"[{name}] tool_results returned: {len(tool_results)} items")
        else:
            if remaining_tool_calls:
                logger.warning(
                    f"[{name}] tool_executor is None! Cannot execute tool calls."
                )

        return tool_results, pending_signal, queued_signals

    async def run_react_loop(
        self,
        llm_with_tools,
        messages: list[dict],
        system_prompt: str,
        provider: str,
        config: dict,
        name: str,
        max_steps: int = 5,
        tool_executor: Any | None = None,
        interceptors: dict[str, Callable] | None = None,
        on_thinking: Callable | None = None,
        model: str | None = None,
        iteration_count: int | None = None,
    ) -> dict:
        from app.core.monitoring.activity import activity_monitor

        messages = [EvoMessageConverter.to_dict(m) for m in messages]
        system_messages = self.build_system_messages(system_prompt, provider)
        history_messages = [m for m in messages if m.get("role") != "system"]
        loop_messages: list[dict] = system_messages + history_messages

        if not history_messages:
            logger.error(f"[{name}] No history messages! Returning empty.")
            return {
                "messages": [],
                "tool_history": [],
                "last_response": None,
                "is_truncated": False,
                "signal": None,
            }

        new_messages: list[dict] = []
        local_tool_history = []
        last_response = None

        logger.info(
            f"[{name}] ▶️ run_react_loop START | iteration={iteration_count} | max_steps={max_steps}"
        )

        for i in range(max_steps):
            logger.info(f"[{name}] 🔄 Step {i + 1}/{max_steps}")
            thread_id = config.get("configurable", {}).get("thread_id")
            run_id = config.get("configurable", {}).get("run_id")
            if thread_id:
                await activity_monitor.check_cancellation(thread_id)

            loop_messages, _ = await self._prepare_turn_context(
                loop_messages=loop_messages,
                model=model,
                name=name,
                thread_id=thread_id,
                run_id=run_id,
                config=config,
            )

            response = await self._execute_llm_call(
                llm_with_tools=llm_with_tools,
                loop_messages=loop_messages,
                config=config,
                name=name,
                system_prompt=system_prompt,
                history_messages=history_messages,
                turn_id=i,
                on_thinking=on_thinking,
                max_steps=max_steps,
            )
            last_response = response

            loop_messages.append(response)
            new_messages.append(response)

            if not response.get("tool_calls"):
                logger.info(f"[{name}] Finished with text response (no tool calls).")
                break

            logger.info(
                f"[{name}] tool_calls detected: {len(response['tool_calls'])} calls"
            )

            (
                tool_results,
                pending_signal,
                queued_signals,
            ) = await self._process_tool_executions(
                response=response,
                name=name,
                config=config,
                interceptors=interceptors,
                tool_executor=tool_executor,
                local_tool_history=local_tool_history,
            )

            for tool_msg in tool_results:
                loop_messages.append(tool_msg)
                new_messages.append(tool_msg)

            if pending_signal is not None:
                return {
                    "messages": new_messages,
                    "tool_history": local_tool_history,
                    "last_response": last_response,
                    "is_truncated": False,
                    "signal": pending_signal,
                    "queued_signals": queued_signals,
                }

        is_truncated = False
        if last_response and last_response.get("tool_calls"):
            logger.error(f"[{name}] Hit max_steps ({max_steps}) with open tool calls.")
            tools_summary = ", ".join(local_tool_history) if local_tool_history else "None"
            truncation_msg = {
                "role": "assistant",
                "content": (
                    f"[TRUNCATION] Agent reached maximum step limit ({max_steps}) "
                    f"with pending tool calls. Tools executed: {tools_summary}."
                ),
                "additional_kwargs": {
                    "is_truncated": True,
                    "max_steps": max_steps,
                    "requires_replan": True,
                }
            }
            new_messages.append(truncation_msg)
            is_truncated = True

        return {
            "messages": new_messages,
            "tool_history": local_tool_history,
            "last_response": last_response,
            "is_truncated": is_truncated,
            "signal": None,
        }

    async def run_single_shot(
        self,
        llm_with_tools,
        messages: list[dict],
        system_prompt: str,
        provider: str,
        config: dict,
        name: str,
        tool_executor: Any | None = None,
        interceptors: dict[str, Callable] | None = None,
    ) -> dict:
        messages = [EvoMessageConverter.to_dict(m) for m in messages]
        system_messages = self.build_system_messages(system_prompt, provider)
        history_messages = [m for m in messages if m.get("role") != "system"]
        loop_messages = system_messages + history_messages

        if not history_messages:
            logger.error(f"[{name}] No history messages! Returning empty.")
            return {
                "messages": [],
                "tool_history": [],
                "last_response": None,
                "is_truncated": False,
            }

        sys_hash = hashlib.md5(system_prompt.encode()).hexdigest()

        response = await self._execute_llm_call(
            llm_with_tools=llm_with_tools,
            loop_messages=loop_messages,
            config=config,
            name=name,
            system_prompt=system_prompt,
            history_messages=history_messages,
            turn_id=0,
            is_single_shot=True,
            sys_hash=sys_hash,
        )

        new_messages = [response]
        local_tool_history = []

        if response.get("tool_calls"):
            tool_results, batch_signal, _ = await self._process_tool_executions(
                response=response,
                name=name,
                config=config,
                interceptors=interceptors,
                tool_executor=tool_executor,
                local_tool_history=local_tool_history,
            )

            for tool_msg in tool_results:
                new_messages.append(tool_msg)
        else:
            batch_signal = None

        return {
            "messages": new_messages,
            "tool_history": local_tool_history,
            "last_response": response,
            "is_truncated": False,
            "signal": batch_signal,
        }
