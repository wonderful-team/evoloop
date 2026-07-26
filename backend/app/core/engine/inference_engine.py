"""
InferenceEngine - Pure LLM execution logic.
"""

import json
import logging
import time
from collections.abc import Callable
from typing import Any

from app.core.engine.callbacks.database_logger import current_node_source
from app.core.engine.context_trimmer import ContextTrimmer, TrimTrigger
from app.core.engine.error_handler import (
    LLM_EXCEPTIONS,
    LLMErrorHandler,
    with_llm_retry,
)
from app.core.engine.message.native_classes import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from app.core.engine.message.reasoning import extract_reasoning_from_message
from app.core.exceptions import InferenceError
from app.core.file import compute_md5
from app.infrastructure.llm.factory import LLMConfig, LLMFactory

logger = logging.getLogger(__name__)


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
    ) -> list[BaseMessage]:
        if provider == "anthropic":
            return [
                SystemMessage(
                    content=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
                )
            ]
        return [SystemMessage(content=system_prompt)]

    async def _prepare_turn_context(
        self,
        loop_messages: list[BaseMessage],
        model: str | None,
        name: str,
        thread_id: str | None,
        run_id: str | None,
        config: dict,
    ) -> tuple[list[BaseMessage], dict[str, Any] | None]:
        if model:
            trim_result = self._context_trimmer.trim(
                messages=loop_messages,
                model=model,
                node_source=name.lower(),
                stages={"window", "repair"},
            )
            if trim_result.trigger != TrimTrigger.NONE:
                from app.core.engine.hooks import HookContext, HookEvent, hook_system

                await hook_system.trigger(
                    HookEvent.PRE_COMPACT,
                    HookContext(
                        thread_id=thread_id,
                        run_id=run_id,
                        messages=trim_result.messages,
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
                for i in range(len(loop_messages) - 1, -1, -1):
                    if loop_messages[i].role == "user":
                        from app.core.engine.context_monitor import ContextMonitor

                        dashboard = "\n\n" + ContextMonitor.calculate(loop_messages, model=model).to_prompt()

                        original_content = loop_messages[i].content
                        if isinstance(original_content, str):
                            new_content = original_content + dashboard
                        elif isinstance(original_content, list):
                            new_content = list(original_content) + [
                                {"type": "text", "text": dashboard.strip()}
                            ]
                        else:
                            break

                        loop_messages[i] = HumanMessage(
                            content=new_content,
                            name=loop_messages[i].name,
                            additional_kwargs=loop_messages[i].additional_kwargs,
                        )
                        break

        msg_count = len(loop_messages)
        if model:
            from app.core.engine.context_monitor import ContextMonitor
            stats = ContextMonitor.calculate(loop_messages, model=model)
            logger.info(
                f"--- {name} Context: {msg_count} msgs, ~{stats.total_tokens} tokens ({stats.usage_ratio * 100:.1f}%) ---"
            )
        else:
            logger.info(f"--- {name} Context: {msg_count} msgs ---")

        return loop_messages, None

    @staticmethod
    def _format_llm_endpoint(llm) -> str:
        return f"model={llm.model or '?'}"

    @staticmethod
    async def _handle_ai_response(response: BaseMessage, handler) -> None:
        if not handler:
            return
        from app.core.engine.message.reasoning import extract_reasoning_from_message
        thinking = extract_reasoning_from_message(response)
        if not response.content and not response.tool_calls and not thinking:
            return
        node_source = current_node_source.get()
        await handler.handle_ai_message(
            content=response.content or "",
            tool_calls=response.tool_calls,
            thinking=thinking,
            metadata=response.metadata,
            node_source=node_source,
        )

    async def _execute_llm_call(
        self,
        llm_with_tools,
        loop_messages: list[BaseMessage],
        config: dict,
        name: str,
        system_prompt: str,
        history_messages: list[BaseMessage],
        turn_id: int,
        on_thinking: Callable | None = None,
        max_steps: int | None = None,
        is_single_shot: bool = False,
        sys_hash: str | None = None,
    ) -> BaseMessage:
        endpoint = self._format_llm_endpoint(llm_with_tools)
        logger.info(f"[{name}] ▶️ LLM call (turn={turn_id}) {endpoint}")

        try:
            start_perf = time.perf_counter()
            response = await self._stream_llm_response(llm_with_tools, loop_messages, config)
            latency = time.perf_counter() - start_perf
            logger.info(f"[{name}] LLM Latency: {latency:.2f}s")
        except LLM_EXCEPTIONS as e:
            err_str = str(e)
            cfg = config.get("configurable", {})
            lightning_base = cfg.get("lightning_base_url", "")
            # Lightning model context limit — fall back to platform model
            if lightning_base and ("n_ctx" in err_str or "context length" in err_str.lower()):
                logger.warning(
                    f"[{name}] Lightning model context limit ({err_str[:100]}), "
                    f"falling back to default model"
                )
                default_model = cfg.get("model", "")
                if default_model:
                    fallback_llm = await self._llm_factory.create_llm(
                        LLMConfig(model_name=default_model, temperature=0.7, streaming=True),
                    )
                    response = await self._stream_llm_response(
                        fallback_llm, loop_messages, config
                    )
                    latency = time.perf_counter() - start_perf
                    logger.info(f"[{name}] Fallback LLM Latency: {latency:.2f}s")
                else:
                    LLMErrorHandler.raise_inference_error(e)
            else:
                LLMErrorHandler.raise_inference_error(e)

        run_id = config.get("configurable", {}).get("run_id")
        if run_id:
            response.additional_kwargs["run_id"] = run_id

        handler = config.get("configurable", {}).get("message_handler")
        if handler:
            await self._handle_ai_response(response, handler)
        if handler and handler.last_persisted_message_id:
            response.id = handler.last_persisted_message_id
            response.additional_kwargs["sequence_number"] = handler.last_persisted_sequence

        thinking_content = extract_reasoning_from_message(response)
        if thinking_content:
            logger.info(f"[{name}] Thinking: {thinking_content[:200]}...")
            if on_thinking:
                await on_thinking(thinking_content)

        return response

    async def _process_tool_executions(
        self,
        response: BaseMessage,
        name: str,
        config: dict,
        interceptors: dict[str, Callable] | None,
        tool_executor: Any | None,
        local_tool_history: list,
    ) -> tuple[list[BaseMessage], Any | None, list[Any]]:
        pending_signal = None
        queued_signals: list[Any] = []
        remaining_tool_calls = []

        tool_calls = response.tool_calls or []
        for tc in tool_calls:
            raw_args = tc.get("args") if isinstance(tc, dict) else None
            if isinstance(raw_args, str):
                try:
                    tc["args"] = json.loads(raw_args)
                except (json.JSONDecodeError, TypeError, ValueError):
                    tc["args"] = {}
            interceptor = (interceptors or {}).get(tc.get("name", ""))
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

        tool_results: list[BaseMessage] = []
        if remaining_tool_calls and tool_executor is not None:
            logger.info(f"[{name}] 🛠   Executing {len(remaining_tool_calls)} tool calls")
            res, batch_signal = await tool_executor.execute_batch(
                remaining_tool_calls, local_tool_history
            )
            tool_results = res

            if batch_signal and pending_signal is None:
                logger.info(f"[{name}] Post-execution signal detected: {type(batch_signal).__name__}")
                pending_signal = batch_signal

            logger.info(f"[{name}] tool_results returned: {len(tool_results)} items")
        else:
            if remaining_tool_calls:
                logger.warning(f"[{name}] tool_executor is None! Cannot execute tool calls.")

        return tool_results, pending_signal, queued_signals

    async def run_react_loop(
        self,
        llm_with_tools,
        messages: list[BaseMessage],
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

        system_messages = self.build_system_messages(system_prompt, provider)
        history_messages = [m for m in messages if m.role != "system"]
        loop_messages: list[BaseMessage] = system_messages + history_messages

        if not history_messages:
            logger.error(f"[{name}] No history messages! Returning empty.")
            return {
                "messages": [],
                "tool_history": [],
                "last_response": None,
                "is_truncated": False,
                "signal": None,
            }

        new_messages: list[BaseMessage] = []
        local_tool_history = []
        last_response = None

        logger.info(f"[{name}] ▶️ run_react_loop START | iteration={iteration_count} | max_steps={max_steps}")

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

            if not response.tool_calls:
                logger.info(f"[{name}] Finished with text response (no tool calls).")
                break

            logger.info(f"[{name}] tool_calls detected: {len(response.tool_calls)} calls")

            tool_results, pending_signal, queued_signals = await self._process_tool_executions(
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
        if last_response and last_response.tool_calls:
            logger.error(f"[{name}] Hit max_steps ({max_steps}) with open tool calls.")
            tools_summary = ", ".join(local_tool_history) if local_tool_history else "None"
            truncation_msg = AIMessage(
                content=(
                    f"[TRUNCATION] Agent reached maximum step limit ({max_steps}) "
                    f"with pending tool calls. Tools executed: {tools_summary}."
                ),
                additional_kwargs={
                    "is_truncated": True,
                    "max_steps": max_steps,
                    "requires_replan": True,
                },
            )
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
        messages: list[BaseMessage],
        system_prompt: str,
        provider: str,
        config: dict,
        name: str,
        tool_executor: Any | None = None,
        interceptors: dict[str, Callable] | None = None,
    ) -> dict:
        system_messages = self.build_system_messages(system_prompt, provider)
        history_messages = [m for m in messages if m.role != "system"]
        loop_messages = system_messages + history_messages

        if not history_messages:
            logger.error(f"[{name}] No history messages! Returning empty.")
            return {
                "messages": [],
                "tool_history": [],
                "last_response": None,
                "is_truncated": False,
            }

        response = await self._execute_llm_call(
            llm_with_tools=llm_with_tools,
            loop_messages=loop_messages,
            config=config,
            name=name,
            system_prompt=system_prompt,
            history_messages=history_messages,
            turn_id=0,
            is_single_shot=True,
            sys_hash=compute_md5(system_prompt),
        )

        new_messages: list[BaseMessage] = [response]
        local_tool_history = []

        if response.tool_calls:
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
