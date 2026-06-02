"""
InferenceEngine - Pure LLM execution logic.

Responsible for:
- LLM initialization and provider detection
- Prompt caching optimizations
- ReAct loop and single-shot execution
- Telemetry recording
- LLM error classification

Explicitly NOT responsible for:
- Message hydration, repair, or windowing
- Signal interception (handled by SignalRegistry via interceptors)
- Blackboard parsing (handled by BlackboardParser)
"""

import hashlib
import logging
import time
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine.context_trimmer import ContextTrimmer, TrimTrigger
from app.core.engine.error_handler import LLMErrorHandler, with_llm_retry
from app.core.engine.message.reasoning import extract_reasoning_from_message
from app.infrastructure.llm.factory import LLMFactory

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
        """Initialize LLM and detect provider."""
        llm = await self._llm_factory.create_llm(model_name=model, temperature=temperature, streaming=streaming)
        provider = self._detect_provider(llm)
        return llm, provider

    def _detect_provider(self, llm) -> str:
        """Detect LLM provider for prompt-caching optimizations."""
        class_name = llm.__class__.__name__
        if "Anthropic" in class_name:
            return "anthropic"
        if "anthropic" in str(getattr(llm, "lc_secrets", {})).lower():
            return "anthropic"
        return "openai"

    def bind_tools(self, llm, tools: list[Any]):
        """Bind tools to LLM and return tool map."""
        if tools:
            return llm.bind_tools(tools), {t.name: t for t in tools}
        return llm, {}

    @staticmethod
    @with_llm_retry(max_attempts=3)
    async def _stream_llm_response(llm_with_tools, loop_messages, config):
        """Stream LLM response and accumulate chunks into a complete AIMessage.

        Uses astream() so on_llm_new_token callbacks fire for real-time
        thinking/streaming display. Falls back to ainvoke() on providers
        that don't support streaming (e.g. kimi with long context).
        """
        from langchain_core.messages import AIMessage, AIMessageChunk

        # astream() triggers on_llm_new_token callbacks for real-time thinking/streaming.
        # AdaptiveChatOpenAI handles retries and parameter reduction internally.
        response = None
        async for chunk in llm_with_tools.astream(loop_messages, config=config):
            if response is None:
                response = chunk
            else:
                response = response + chunk

        # Convert accumulated chunk to a proper AIMessage for downstream compatibility
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
    ) -> list[SystemMessage]:
        """Build provider-optimized system messages."""
        if provider == "anthropic":
            return [
                SystemMessage(
                    content=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ]
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
        config: RunnableConfig,
    ) -> tuple[list[BaseMessage], dict[str, Any] | None]:
        """Trims context and calculates usage metrics."""
        if model:
            trim_result = self._context_trimmer.trim(
                messages=loop_messages,
                model=model,
                node_source=name.lower(),  # type: ignore[arg-type]
                stages={"window", "repair"},
            )
            if trim_result.trigger != TrimTrigger.NONE:
                # Trigger PRE_COMPACT hook BEFORE applying the trim to save state
                from app.core.engine.hooks import HookContext, HookEvent, hook_system

                await hook_system.trigger(
                    HookEvent.PRE_COMPACT,
                    HookContext(
                        thread_id=thread_id,
                        run_id=run_id,
                        messages=loop_messages,
                        project_id=config.get("configurable", {}).get("project_id"),
                        user_id=config.get("configurable", {}).get("user_id"),
                        compact_trigger=trim_result.trigger.name.lower(),
                    ),
                )

                loop_messages = trim_result.messages
                logger.info(
                    f"[{name}] ✂️ Loop trim: {trim_result.before_count} -> {trim_result.after_count} msgs, "
                    f"{trim_result.before_tokens} -> {trim_result.after_tokens} tokens"
                )

            # --- Cognitive Enhancement: Inject Context Dashboard into the message stream ---
            # We inject this into the last HumanMessage (usually the context_ticket)
            # so the Agent sees it as part of its current 'world state'.
            if loop_messages:
                # Find the last HumanMessage to append the dashboard
                for i in range(len(loop_messages) - 1, -1, -1):
                    if isinstance(loop_messages[i], HumanMessage):
                        from app.core.engine.context_monitor import ContextMonitor

                        dashboard = (
                            "\n\n"
                            + ContextMonitor.calculate(
                                loop_messages, model=model
                            ).to_prompt()
                        )

                        # Create a new message with appended dashboard to avoid side effects on the original history
                        original_msg = loop_messages[i]
                        original_content = original_msg.content
                        if isinstance(original_content, str):
                            new_content = original_content + dashboard
                        elif isinstance(original_content, list):
                            new_content = list(original_content) + [
                                {"type": "text", "text": dashboard.strip()}
                            ]
                        else:
                            # Skip dashboard injection for other non-string/non-list content
                            # to avoid corrupting message format expected by the LLM provider
                            logger.debug(
                                f"[{name}] Skipping dashboard injection: "
                                f"HumanMessage content is {type(original_content).__name__}, not str or list"
                            )
                            break
                        loop_messages[i] = HumanMessage(
                            content=new_content,
                            name=original_msg.name,
                            additional_kwargs=original_msg.additional_kwargs,
                        )
                        break

        # DEBUG: Check loop_messages before returning
        for idx, msg in enumerate(loop_messages):
            if not isinstance(msg, BaseMessage):
                logger.error(
                    f"[{name}] 🚨 _prepare_turn_context returning non-BaseMessage at index {idx}: "
                    f"type={type(msg).__name__}, repr={repr(msg)[:200]}"
                )

        # Log context window size before each LLM call
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

    async def _execute_llm_call(
        self,
        llm_with_tools,
        loop_messages: list[BaseMessage],
        config: RunnableConfig,
        name: str,
        system_prompt: str,
        history_messages: list[BaseMessage],
        turn_id: int,
        on_thinking: Callable | None = None,
        max_steps: int | None = None,
        is_single_shot: bool = False,
        sys_hash: str | None = None,
    ) -> AIMessage:
        """Executes LLM call and extracts reasoning."""
        try:
            start_perf = time.perf_counter()
            response = await self._stream_llm_response(llm_with_tools, loop_messages, config)
            latency = time.perf_counter() - start_perf
            logger.info(f"[{name}] ⏱️ LLM Latency: {latency:.2f}s")

            if is_single_shot and sys_hash:
                logger.warning(f"[{name}] PROMPT CACHE DIAGNOSTIC: SystemPromptHash={sys_hash} | Latency={latency:.2f}s")

            # [DIAGNOSTIC] Deep inspection of raw response
            logger.debug(
                f"[{name}] 🔍 RAW RESPONSE DIAGNOSTIC:\n"
                f"  - Content length: {len(response.content)}\n"
                f"  - Tool Calls: {response.tool_calls}\n"
                f"  - Invalid Tool Calls: {response.invalid_tool_calls}\n"
                f"  - Additional Kwargs: {list(response.additional_kwargs.keys())}\n"
                f"  - Finish Reason: {response.response_metadata.get('finish_reason')}\n"
                f"  - Model Metadata: {response.response_metadata}\n"
            )

        except Exception as e:
            LLMErrorHandler.raise_inference_error(e)

        # Inject run_id
        run_id = config.get("configurable", {}).get("run_id")
        if run_id:
            response.additional_kwargs["run_id"] = run_id

        # Backfill DB-assigned id and sequence_number from MessageHandler.
        # _stream_llm_response creates a fresh AIMessage from accumulated chunks,
        # which does NOT inherit the values set by on_llm_end on generation.message.
        # Without this, FinishNode._mark_turn_summary can't find the message.
        handler = config.get("configurable", {}).get("message_handler")
        if handler and handler.last_persisted_message_id:
            response.id = handler.last_persisted_message_id
            response.additional_kwargs["sequence_number"] = (
                handler.last_persisted_sequence
            )

        # Extract thinking content using unified utility
        thinking_content = extract_reasoning_from_message(response)
        if thinking_content:
            logger.info(f"[{name}] Thinking: {thinking_content[:200]}...")
            if on_thinking:
                await on_thinking(thinking_content)

        return response

    async def _process_tool_executions(
        self,
        response: AIMessage,
        name: str,
        config: RunnableConfig,
        interceptors: dict[str, Callable] | None,
        tool_executor: Any | None,
        local_tool_history: list,
    ) -> tuple[list[BaseMessage], Any | None, list[Any]]:
        """Processes tool calls, handles interceptors, and executes tools.

        Returns:
            (tool_results, primary_signal, queued_signals)
            queued_signals: additional signals captured in the same turn that would
            previously have been silently dropped. SupervisorNode persists these to
            blackboard.pending_signals so they can be drained serially without
            re-running the Supervisor LLM.
        """
        pending_signal = None
        queued_signals: list[Any] = []
        remaining_tool_calls = []

        for tc in response.tool_calls:
            interceptor = (interceptors or {}).get(tc["name"])
            if interceptor:
                sig = await interceptor(tc, config)
                if sig is not None:
                    if pending_signal is None:
                        pending_signal = sig  # first signal fires immediately
                    else:
                        logger.info(f"[{name}] Queuing additional signal: {tc['name']}")
                        queued_signals.append(sig)  # subsequent signals are queued
                    continue

            remaining_tool_calls.append(tc)

        tool_results = []
        if remaining_tool_calls and tool_executor is not None:
            logger.info(
                f"[{name}] 🛠️ Executing {len(remaining_tool_calls)} tool calls via tool_executor"
            )
            res, batch_signal = await tool_executor.execute_batch(
                remaining_tool_calls, local_tool_history
            )
            tool_results = res

            if batch_signal and pending_signal is None:
                logger.info(
                    f"[{name}] ⚡ Post-execution signal detected: {type(batch_signal).__name__}"
                )
                pending_signal = batch_signal

            logger.info(f"[{name}] 📦 tool_results returned: {len(tool_results)} items")
            for tool_msg in tool_results:
                logger.info(
                    f"[{name}] Result ({tool_msg.name}): {str(tool_msg.content)[:200]}..."
                )
        else:
            if remaining_tool_calls:
                logger.warning(
                    f"[{name}] ⚠️ tool_executor is None! Cannot execute {len(remaining_tool_calls)} tool calls."
                )
            else:
                logger.info(f"[{name}] ℹ️ No remaining tool_calls after interception.")

        return tool_results, pending_signal, queued_signals

    async def run_react_loop(
        self,
        llm_with_tools,
        messages: list[BaseMessage],
        system_prompt: str,
        provider: str,
        config: RunnableConfig,
        name: str,
        max_steps: int = 5,
        tool_executor: Any | None = None,
        interceptors: dict[str, Callable] | None = None,
        on_thinking: Callable | None = None,
        model: str | None = None,
        iteration_count: int | None = None,
    ) -> dict:
        """
        Core ReAct loop.

        Returns:
            dict with keys: messages, tool_history, last_response, is_truncated, signal
        """
        from app.core.monitoring.activity import activity_monitor

        system_messages = self.build_system_messages(system_prompt, provider)
        history_messages = [m for m in messages if not isinstance(m, SystemMessage)]
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

        logger.info(
            f"[{name}] ▶️ run_react_loop START | iteration={iteration_count} | model={model} | max_steps={max_steps} | msg_count={len(messages)} | tool_executor={'YES' if tool_executor else 'NO'}"
        )

        for i in range(max_steps):
            logger.info(
                f"[{name}] 🔄 Step {i + 1}/{max_steps} (Iteration {iteration_count})"
            )
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
                finish_reason = response.response_metadata.get("finish_reason")
                if finish_reason == "pause_turn":
                    # kimi-k2-thinking-turbo may return pause_turn when it pauses during
                    # reasoning without emitting tool_calls yet. Continue the loop so
                    # the model can complete its thought and emit tools on the next turn.
                    logger.info(
                        f"[{name}] ⏸️ Model paused (pause_turn), continuing loop..."
                    )
                    continue
                logger.info(f"[{name}] Finished with text response (no tool calls).")
                break

            logger.info(
                f"[{name}] 🔧 tool_calls detected: {len(response.tool_calls)} calls"
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
        if last_response and last_response.tool_calls:
            logger.error(f"[{name}] Hit max_steps ({max_steps}) with open tool calls.")
            tools_summary = (
                ", ".join(local_tool_history) if local_tool_history else "None"
            )
            truncation_msg = AIMessage(
                content=(
                    f"[TRUNCATION] Agent reached the maximum step limit ({max_steps}) "
                    f"with pending tool calls. The task may be incomplete or stuck in a loop. "
                    f"Tools executed in this batch: {tools_summary}. "
                    f"Supervisor review and replanning is required."
                ),
                additional_kwargs={
                    "is_truncated": True,
                    "max_steps": max_steps,
                    "requires_replan": True,
                },
            )
            new_messages.append(truncation_msg)
            is_truncated = True

        logger.info(
            f"[{name}] ⏹️ run_react_loop END | new_messages={len(new_messages)} | "
            f"types={[type(m).__name__ for m in new_messages]} | "
            f"truncated={is_truncated}"
        )
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
        config: RunnableConfig,
        name: str,
        tool_executor: Any | None = None,
        interceptors: dict[str, Callable] | None = None,
    ) -> dict:
        """Single-shot execution for subtasks."""
        system_messages = self.build_system_messages(system_prompt, provider)
        history_messages = [m for m in messages if not isinstance(m, SystemMessage)]
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
