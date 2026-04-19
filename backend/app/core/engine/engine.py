"""
AgentEngine - Instance-based execution engine for EvoLoop Agents.
"""

import asyncio
import json
import logging
import re
import time
from typing import Any, Optional

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from pydantic import Field

from app.constants import DEFAULT_CONTEXT_LIMIT, DEFAULT_WINDOW_SIZE, NODE_WINDOW_SIZES
from app.core.engine.message_utils import apply_forgotten_status, repair_message_history, smart_window_slice
from app.core.engine.signals import AgentSignal
from app.core.engine.signals import signal_manager
from app.core.engine.state import AgentState, BlackboardState, ensure_state, RunnableConfigMetadata
from app.core.engine.state.history import ToolCall
from app.core.engine.tools import AgentToolExecutor, ToolExecutionResult
from app.core.memory.tool_output_memory import get_tool_memory_from_state
from app.core.monitoring.activity import activity_monitor
from app.core.monitoring.telemetry import agent_telemetry
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.llm.factory import LLMFactory
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


class EngineResult(DynamicBaseModel):
    """Structured result from AgentEngine.run_node() and internal execution methods."""
    messages: list[Any] = Field(default_factory=list)
    tool_history: list[str] = Field(default_factory=list)
    blackboard: BlackboardState | None = None
    is_truncated: bool = False
    signal: AgentSignal | None = None
    routing_target: str | None = None


class AgentEngine:
    """
    Instance-based execution engine for EvoLoop Agents.

    Supports dependency injection for easier testing and extensibility.
    """

    def __init__(
        self,
        llm_factory: Any | None = None,
        config_service: Any | None = None,
        tool_executor_class: type = AgentToolExecutor,
        enable_diff_tracking: bool = True,
    ):
        """
        Initialize AgentEngine with optional dependency injection.

        Args:
            llm_factory: Optional LLM factory (defaults to LLMFactory)
            config_service: Optional config service (defaults to SystemConfigService)
            tool_executor_class: Tool executor class (defaults to AgentToolExecutor)
            enable_diff_tracking: Whether to enable diff tracking for file operations
        """
        self._llm_factory = llm_factory or LLMFactory
        self._config_service = config_service or SystemConfigService
        self._tool_executor_class = tool_executor_class
        self._enable_diff_tracking = enable_diff_tracking

    @staticmethod
    def _normalize_tool_calls(raw_tool_calls: list[dict[str, Any]] | None) -> list[ToolCall]:
        """Convert LangChain raw tool call dicts into structured ToolCall models."""
        if not raw_tool_calls:
            return []

        normalized = []
        for tc in raw_tool_calls:
            if isinstance(tc, ToolCall):
                normalized.append(tc)
            else:
                normalized.append(ToolCall(
                    id=tc.get("id", gen_uuid()),
                    name=tc.get("name", ""),
                    args=tc.get("args", {}),
                ))

        return normalized

    async def run_node(
        self,
        state: AgentState,
        config: RunnableConfig,
        system_prompt: str,
        tools: list[Any],
        model: str = None,
        max_steps: int = 5,
        temperature: float = 0.7,
        name: str = "Agent",
        is_subtask: bool = False,
        node_source: str = None,
        parallel_tools: bool = False,
    ) -> EngineResult:
        """Executes the standard Agent ReAct loop."""
        # 1. Initialize LLM (with instance caching for performance)
        config_meta = RunnableConfigMetadata.from_config(config)
        if model is None:
            model = config_meta.model

        llm = await self._llm_factory.create_llm(model_name=model, temperature=temperature)

        # 1 Detect Provider for Prompt Caching
        provider = self._detect_provider(llm)

        if tools:
            llm_with_tools = llm.bind_tools(tools)
            tool_map = {t.name: t for t in tools}
        else:
            llm_with_tools = llm
            tool_map = {}

        # 2. Config & Context
        from app.core.engine.context_hydrator import EvoContextMiddleware
        state = ensure_state(state)
        # [MSG-TRACE] ENGINE ENTER
        _in_msgs = state.messages or []
        logger.info(f"[MSG-TRACE][{name}] ENGINE_ENTER state.messages: {len(_in_msgs)} msgs | types={[type(m).__name__ for m in _in_msgs]} | ids={[getattr(m,'id','N/A')[:8] if getattr(m,'id',None) else 'N/A' for m in _in_msgs]} | contents={[str(getattr(m,'content',''))[:60] for m in _in_msgs]}")
        state = await EvoContextMiddleware.hydrate(state, config)
        logger.info(f"[{name}] 🧪 Context Hydrated via Middleware")

        # 3. Message Handling & Repair
        repaired_messages = await self._prepare_message_pipeline(
            state, config_meta, model, node_source, name
        )
        # [MSG-TRACE] ENGINE PIPELINE
        logger.info(f"[MSG-TRACE][{name}] ENGINE_PIPELINE repaired_messages: {len(repaired_messages)} msgs | types={[type(m).__name__ for m in repaired_messages]} | ids={[getattr(m,'id','N/A')[:8] if getattr(m,'id',None) else 'N/A' for m in repaired_messages]} | contents={[str(getattr(m,'content',''))[:60] for m in repaired_messages]}")

        # 4. Execution Mode Selection
        if is_subtask:
            logger.info(f"[{name}] 🎯 Single-shot mode (subtask) - executing immediately")
            result = await self._execute_single_shot(
                llm_with_tools=llm_with_tools,
                tool_map=tool_map,
                messages=repaired_messages,
                system_prompt=system_prompt,
                provider=provider, # Pass detected provider
                config=config,
                config_meta=config_meta,
                name=name,
                state=state,
                parallel_tools=parallel_tools,
            )
        else:
            result = await self._execute_react_loop(
                llm_with_tools=llm_with_tools,
                tool_map=tool_map,
                messages=repaired_messages,
                system_prompt=system_prompt,
                provider=provider, # Pass detected provider
                config=config,
                config_meta=config_meta,
                max_steps=max_steps,
                name=name,
                state=state,
                parallel_tools=parallel_tools,
            )

        self._apply_node_source_marker(result.messages, node_source)
        # [MSG-TRACE] ENGINE EXIT
        _res_msgs = result.messages or []
        logger.info(f"[MSG-TRACE][{name}] ENGINE_EXIT result.messages: {len(_res_msgs)} msgs | types={[type(m).__name__ for m in _res_msgs]} | ids={[getattr(m,'id','N/A')[:8] if getattr(m,'id',None) else 'N/A' for m in _res_msgs]} | contents={[str(getattr(m,'content',''))[:60] for m in _res_msgs]} | signal={type(result.signal).__name__ if result.signal else 'None'}")
        return result

    def _get_evoloop_handler(self, config: RunnableConfig) -> "TransparentCallbackHandler | None":
        """Extract TransparentCallbackHandler from config callbacks for observability."""
        from app.core.engine.callbacks.transparent import TransparentCallbackHandler
        callbacks = config.get("callbacks", []) if config else []
        callback_list = callbacks if isinstance(callbacks, list) else getattr(callbacks, "handlers", [])
        for cb in callback_list:
            if isinstance(cb, TransparentCallbackHandler):
                return cb
        return None

    async def _intercept_signals(
        self,
        tool_calls: list[ToolCall],
        evoloop_handler: "TransparentCallbackHandler | None",
        new_messages: list[BaseMessage],
    ) -> tuple["AgentSignal | None", list[str]]:
        """Intercept pre-execution signals and append synthetic ToolMessages.

        Returns:
            (pending_signal, signal_tool_names)
        """
        signal_tools = []
        pending_signal = None
        for tc in tool_calls:
            signal = await signal_manager.intercept(tc)
            if signal:
                if evoloop_handler:
                    try:
                        await evoloop_handler.on_tool_start(
                            serialized={"name": tc.name},
                            input_str=json.dumps(tc.args, ensure_ascii=False),
                            run_id=tc.id
                        )
                    except Exception as e:
                        logger.error(f"Failed to log intercepted tool start: {e}")

                pending_signal = signal
                output_msg = f"Signal emitted: {tc.name}"
                new_messages.append(ToolMessage(
                    content=output_msg,
                    tool_call_id=tc.id,
                    name=tc.name,
                    id=gen_uuid(),
                ))

                if evoloop_handler:
                    try:
                        await evoloop_handler.on_tool_end(output=output_msg, run_id=tc.id)
                    except Exception as e:
                        logger.error(f"Failed to log intercepted tool end: {e}")

                signal_tools.append(tc.name)
                break

        return pending_signal, signal_tools

    async def _execute_tool_calls(
        self,
        remaining_tool_calls: list[ToolCall],
        tool_map: dict[str, Any],
        state: AgentState,
        config: RunnableConfig,
        name: str,
        local_tool_history: list[str],
        parallel_tools: bool,
        loop_messages: list[BaseMessage] | None = None,
        existing_signal: "AgentSignal | None" = None,
    ) -> tuple[list[BaseMessage], "AgentSignal | None"]:
        """Execute remaining tool calls (parallel or sequential).

        Returns:
            (tool_result_messages, pending_post_signal)
        """
        tool_executor = self._tool_executor_class(
            tool_map=tool_map,
            state=state,
            config=config,
            name=name,
            enable_diff_tracking=self._enable_diff_tracking,
        )

        async def _process_single_tool(tc: ToolCall) -> "ToolExecutionResult":
            return await tool_executor.execute_tool(
                tool_name=tc.name,
                tool_args=tc.args,
                tool_id=tc.id,
                local_tool_history=local_tool_history,
            )

        if parallel_tools:
            logger.info(f"[{name}] ⚡ Executing {len(remaining_tool_calls)} tools in parallel")
            tool_results = await asyncio.gather(*[_process_single_tool(tc) for tc in remaining_tool_calls])
        else:
            logger.info(f"[{name}] ⛓️ Executing {len(remaining_tool_calls)} tools sequentially")
            tool_results = []
            for tc in remaining_tool_calls:
                res = await _process_single_tool(tc)
                tool_results.append(res)

        new_tool_messages = []
        pending_signal = existing_signal
        for res in tool_results:
            tool_msg = res.message
            raw_content = res.raw_result

            logger.info(f"[{name}] ✅ Result ({tool_msg.name}): {str(tool_msg.content[:300])}...")
            if loop_messages is not None:
                loop_messages.append(tool_msg)
            new_tool_messages.append(tool_msg)

            if not pending_signal:
                signal = signal_manager.detect_post_execution_signal(tool_msg.name, raw_content)
                if signal:
                    pending_signal = signal

        return new_tool_messages, pending_signal

    @staticmethod
    def _inject_run_id(response: AIMessage, run_id: str | None) -> None:
        """Inject run_id into response metadata and additional_kwargs."""
        if run_id:
            if not hasattr(response, "metadata"):
                response.metadata = {}
            response.metadata["run_id"] = run_id
            if not hasattr(response, "additional_kwargs"):
                response.additional_kwargs = {}
            response.additional_kwargs["run_id"] = run_id

    @staticmethod
    def _apply_node_source_marker(messages: list[Any], node_source: str | None) -> None:
        """Inject node_source metadata into AI messages in-place."""
        if not node_source:
            return

        for msg in messages or []:
            if isinstance(msg, AIMessage) and msg.content:
                if not hasattr(msg, "metadata") or msg.metadata is None:
                    msg.metadata = {}
                msg.metadata["node_source"] = node_source

    @staticmethod
    def _detect_provider(llm) -> str:
        """Detect LLM provider for prompt-caching optimizations."""
        class_name = llm.__class__.__name__
        if "Anthropic" in class_name:
            return "anthropic"
        elif hasattr(llm, "lc_secrets") and "anthropic" in str(llm.lc_secrets).lower():
            return "anthropic"
        return "openai"

    def _prepare_messages(
        self,
        state: AgentState,
        system_prompt: str,
        messages: list[BaseMessage],
        provider: str,
        name: str,
    ) -> tuple[list[BaseMessage], list[BaseMessage], list[BaseMessage]]:
        """Build system messages, filter history, and assemble loop messages.

        Returns:
            (system_messages, history_messages, loop_messages)
            Caller should check if history_messages is empty and return early.
        """
        state = ensure_state(state)
        system_messages = self._build_system_messages(system_prompt, messages, provider)
        history_messages = [m for m in messages if not isinstance(m, SystemMessage)]
        loop_messages = system_messages + history_messages
        if not history_messages:
            logger.error(f"[{name}] 🔴 No history messages! Returning empty.")
        return system_messages, history_messages, loop_messages

    async def _prepare_message_pipeline(
        self,
        state: AgentState,
        config_meta: RunnableConfigMetadata,
        model: str,
        node_source: str | None,
        name: str,
    ) -> list[BaseMessage]:
        """Run the full message preparation pipeline: diagnostic, forgetting, windowing, repair."""
        raw_messages = list(state.messages)
        logger.info(f"[{name}] 📨 Raw messages: {len(raw_messages)} | Types: {[type(m).__name__ for m in raw_messages]}")

        for i, m in enumerate(raw_messages):
            msg_meta = getattr(m, "metadata", {})
            logger.info(f"[{name}] 🔍 MSG[{i}] Role: {type(m).__name__} | Content: {m.content}... | Meta: {msg_meta}")

        tool_memory = get_tool_memory_from_state(state)
        messages_with_forgetting = apply_forgotten_status(raw_messages, tool_memory)
        logger.info(f"[{name}] 🧠 After forgetting: {len(messages_with_forgetting)} messages")

        effective_window = NODE_WINDOW_SIZES.get(node_source, DEFAULT_WINDOW_SIZE)
        windowed_messages = await smart_window_slice(
            messages_with_forgetting,
            window_size=effective_window,
            max_total_chars=DEFAULT_CONTEXT_LIMIT,
            model=model,
            node_source=node_source or "default",
            thread_id=config_meta.thread_id,
            user_id=config_meta.user_id,
            project_id=config_meta.project_id,
        )

        logger.info(
            f"[{name}] 📐 Window: {len(messages_with_forgetting)} -> {len(windowed_messages)} messages "
            f"(forgotten: {len(tool_memory.forgotten)}, node={node_source}, window={effective_window})"
        )

        return repair_message_history(windowed_messages)

    async def _invoke_llm(
        self,
        llm_with_tools,
        messages: list[BaseMessage],
        system_prompt: str,
        history_messages: list[BaseMessage],
        config: RunnableConfig,
        name: str,
        node_name: str,
        turn_id: int,
        telemetry_metadata: dict,
    ) -> AIMessage:
        """Invoke LLM, log prompt-cache diagnostics (optional), and record telemetry.

        Raises:
            Exception: On LLM invocation failure (caller should handle via _handle_llm_exception).
        """
        start_perf = time.perf_counter()
        response = await llm_with_tools.ainvoke(messages, config=config)
        latency = time.perf_counter() - start_perf

        agent_telemetry.record_inference(
            node_name=node_name,
            turn_id=turn_id,
            prompt_info={
                "system_len": len(system_prompt),
                "history_len": sum(len(str(m.content)) for m in history_messages),
                "total_len": len(system_prompt) + sum(len(str(m.content)) for m in messages)
            },
            response_info={
                "content": response.content,
                "usage": getattr(response, "usage_metadata", {}),
                "is_tool_call": bool(response.tool_calls),
                "tool_names": [tc.name for tc in self._normalize_tool_calls(response.tool_calls)]
            },
            latency_ms=latency * 1000,
            metadata=telemetry_metadata
        )
        return response

    def _update_blackboard_from_response(
        self,
        response: AIMessage,
        state: AgentState,
        name: str,
        verbose: bool = True,
    ) -> None:
        """Parse thinking content from LLM response and update blackboard."""
        if verbose:
            content_preview = str(response.content)[:200] if response.content else "(empty)"
            tool_calls_count = len(response.tool_calls) if hasattr(response, 'tool_calls') and response.tool_calls else 0
            logger.info(f"[{name}] 📥 LLM response: content='{content_preview}...', tool_calls={tool_calls_count}")

        thinking_content = response.content or ""
        if not thinking_content and verbose:
            if hasattr(response, "additional_kwargs") and "thought" in response.additional_kwargs:
                thinking_content = response.additional_kwargs["thought"]
                logger.info(f"[{name}] 🧠 Thinking (from additional_kwargs): {thinking_content[:200]}...")

        if thinking_content:
            if verbose:
                logger.info(f"[{name}] 🧠 Thinking: {thinking_content}")
            state.blackboard = self._parse_inferred_blackboard(
                thinking_content, state.blackboard, name
            )

    async def _execute_react_loop(
        self,
        llm_with_tools,
        tool_map: dict[str, Any],
        messages: list[BaseMessage],
        system_prompt: str,
        provider: str, # Added provider
        config: RunnableConfig,
        config_meta: RunnableConfigMetadata,
        name: str,
        state: AgentState,
        max_steps: int = 10,
        parallel_tools: bool = True,
    ) -> EngineResult:
        """Core ReAct Loop Logic."""
        system_messages, history_messages, loop_messages = self._prepare_messages(
            state, system_prompt, messages, provider, name
        )
        if not history_messages:
            return EngineResult(messages=[])

        new_messages = []
        local_tool_history = []
        last_response = None

        for i in range(max_steps):
            # Check for cancellation
            if config_meta.thread_id:
                await activity_monitor.check_cancellation(config_meta.thread_id)

            logger.info(f"--- {name} Loop Step {i+1} ---")
            # [MSG-TRACE] LOOP START
            logger.info(f"[MSG-TRACE][{name}] LOOP_STEP_{i+1} loop_messages: {len(loop_messages)} msgs | types={[type(m).__name__ for m in loop_messages]} | ids={[getattr(m,'id','N/A')[:8] if getattr(m,'id',None) else 'N/A' for m in loop_messages]}")

            try:
                response = await self._invoke_llm(
                    llm_with_tools,
                    loop_messages,
                    system_prompt,
                    history_messages,
                    config,
                    name,
                    node_name=name,
                    turn_id=i,
                    telemetry_metadata={"max_steps": max_steps, "parallel_tools": parallel_tools},
                )
                last_response = response
            except Exception as e:
                handler = config.get("configurable", {}).get("message_handler")
                return await self._handle_llm_exception(e, name, state, handler=handler)

            self._inject_run_id(response, config_meta.run_id)
            self._update_blackboard_from_response(response, state, name)

            loop_messages.append(response)
            new_messages.append(response)
            # [MSG-TRACE] AFTER LLM RESPONSE
            logger.info(f"[MSG-TRACE][{name}] LOOP_STEP_{i+1} new_messages after LLM: {len(new_messages)} msgs | types={[type(m).__name__ for m in new_messages]} | ids={[getattr(m,'id','N/A')[:8] if getattr(m,'id',None) else 'N/A' for m in new_messages]} | contents={[str(getattr(m,'content',''))[:60] for m in new_messages]}")

            if not response.tool_calls:
                logger.info(f"[{name}] 🏁 Finished with text response (no tool calls).")
                break

            tool_calls = self._normalize_tool_calls(response.tool_calls)

            pending_signal, signal_tools = await self._intercept_signals(
                tool_calls, self._get_evoloop_handler(config), new_messages
            )

            remaining_tool_calls = [tc for tc in tool_calls if tc.name not in signal_tools]
            if remaining_tool_calls:
                tool_msgs, pending_signal = await self._execute_tool_calls(
                    remaining_tool_calls,
                    tool_map,
                    state,
                    config,
                    name,
                    local_tool_history,
                    parallel_tools,
                    loop_messages=loop_messages,
                    existing_signal=pending_signal,
                )
                new_messages.extend(tool_msgs)
                # [MSG-TRACE] AFTER TOOL EXECUTION
                logger.info(f"[MSG-TRACE][{name}] LOOP_STEP_{i+1} new_messages after tools: {len(new_messages)} msgs | types={[type(m).__name__ for m in new_messages]} | ids={[getattr(m,'id','N/A')[:8] if getattr(m,'id',None) else 'N/A' for m in new_messages]} | contents={[str(getattr(m,'content',''))[:60] for m in new_messages]}")

            # 4. Dispatch Signal if present after tool execution
            if pending_signal:
                # [MSG-TRACE] SIGNAL RETURN
                logger.info(f"[MSG-TRACE][{name}] LOOP_STEP_{i+1} SIGNAL_RETURN new_messages: {len(new_messages)} msgs | types={[type(m).__name__ for m in new_messages]} | signal={type(pending_signal).__name__}")
                return EngineResult(
                    messages=new_messages,
                    signal=pending_signal,
                    tool_history=local_tool_history,
                    blackboard=state.blackboard,
                )

        # Loop ended
        is_truncated = False
        if last_response and last_response.tool_calls:
            logger.error(f"[{name}] 🔴 Hit max_steps ({max_steps}) with open tool calls.")
            truncation_msg = AIMessage(
                content="Execution reached maximum step limit and was paused.",
                metadata={"is_truncated": True, "max_steps": max_steps}
            )
            new_messages.append(truncation_msg)
            is_truncated = True

        # [MSG-TRACE] LOOP END
        logger.info(f"[MSG-TRACE][{name}] LOOP_END new_messages: {len(new_messages)} msgs | types={[type(m).__name__ for m in new_messages]} | ids={[getattr(m,'id','N/A')[:8] if getattr(m,'id',None) else 'N/A' for m in new_messages]} | contents={[str(getattr(m,'content',''))[:60] for m in new_messages]}")
        return EngineResult(
            messages=new_messages,
            tool_history=local_tool_history,
            blackboard=state.blackboard,
            is_truncated=is_truncated,
        )

    async def _execute_single_shot(
        self,
        llm_with_tools,
        tool_map: dict[str, Any],
        messages: list[BaseMessage],
        system_prompt: str,
        provider: str, # Added provider
        config: RunnableConfig,
        config_meta: RunnableConfigMetadata,
        name: str,
        state: AgentState,
        parallel_tools: bool = False,
    ) -> EngineResult:
        """Single-shot execution for subtasks."""
        system_messages, history_messages, loop_messages = self._prepare_messages(
            state, system_prompt, messages, provider, name
        )
        if not history_messages:
            return EngineResult(messages=[])

        try:
            response = await self._invoke_llm(
                llm_with_tools,
                loop_messages,
                system_prompt,
                history_messages,
                config,
                name,
                node_name=f"{name}_subtask",
                turn_id=0,
                telemetry_metadata={"is_single_shot": True},
            )
        except Exception as e:
            handler = config.get("configurable", {}).get("message_handler")
            return await self._handle_llm_exception(e, name, state, handler=handler)

        new_messages = [response]
        local_tool_history = []

        self._inject_run_id(response, config_meta.run_id)
        self._update_blackboard_from_response(response, state, name, verbose=False)
        tool_calls = self._normalize_tool_calls(response.tool_calls)
        pending_signal, signal_tools = await self._intercept_signals(
            tool_calls, self._get_evoloop_handler(config), new_messages
        )

        remaining_tool_calls = [tc for tc in tool_calls if tc.name not in signal_tools]
        if remaining_tool_calls:
            tool_msgs, pending_signal = await self._execute_tool_calls(
                remaining_tool_calls,
                tool_map,
                state,
                config,
                name,
                local_tool_history,
                parallel_tools,
                existing_signal=pending_signal,
            )
            new_messages.extend(tool_msgs)

        # 3. Protocol Violation Check (Subtask MUST result in a signal or tool execution)
        if not pending_signal and not tool_calls:
            logger.error(f"[{name}] 🛑 SINGLE-SHOT VIOLATION: Subtask did not call any tool!")
            new_messages.append(AIMessage(content="Subtask failed: No tool was invoked."))
            return EngineResult(
                messages=new_messages,
                tool_history=local_tool_history,
                blackboard=state.blackboard,
            )

        logger.info(f"[{name}] ✓ Single-shot complete. {len(response.tool_calls)} tool(s) executed.")

        return EngineResult(
            messages=new_messages,
            tool_history=local_tool_history,
            blackboard=state.blackboard,
            signal=pending_signal,
        )

    def _build_system_messages(self, system_prompt: str, messages: list, provider: str) -> list[BaseMessage]:
        """
        Builds system messages optimized for Prompt Caching.
        Decouples static instructions from dynamic telemetry to maximize cache hit rates.
        """
        if provider == "anthropic":
            return [SystemMessage(content=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"}
            }])]
        else:
            return [SystemMessage(content=system_prompt)]

    async def _handle_llm_exception(self, e: Exception, name: str, state: AgentState, handler: Any = None) -> EngineResult:
        """Centralized handling for LLM invocation exceptions using LLMErrorHandler."""
        from app.core.engine.error_handler import LLMErrorHandler
        from app.i18n.service import i18n

        logger.error(f"[{name}] LLM invocation failed: {e}")

        # Use the centralized classifier
        classification = LLMErrorHandler.classify_exception(e)

        # 1. Report error to the unified message handler for immediate UI feedback (SSE/Persistence)
        if handler:
            await handler.handle_error(e)

        # 2. Bubble up terminal errors to trigger specialized UI (quota/auth) in the background orchestrator
        if classification.is_terminal:
            from app.core.context import ContextManager
            ctx = ContextManager.current()
            if ctx:
                ctx.terminal_error = classification.error_type
                logger.info(f"[{name}] 🚫 Terminal error '{classification.error_type}' recorded in context for circuit breaking.")

            logger.warning(f"[{name}] Terminal LLM error detected ({classification.error_type}). Bubbling up to orchestrator.")
            raise e

        icon_failed = i18n.get("icons.failed") or "❌"

        # Construct a rich error message for the AI message content
        user_friendly_msg = f"{icon_failed} **{classification.title}**: {classification.message}\n\n{classification.hint}\n\n> {classification.raw_error[:200]}"

        return EngineResult(
            messages=[AIMessage(
                content=user_friendly_msg,
                metadata={
                    "is_error": True,
                    "is_terminal": classification.is_terminal,
                    "error_type": classification.error_type,
                    "status_code": classification.status_code,
                    "raw_error": classification.raw_error
                }
            )],
            tool_history=[],
            blackboard=state.blackboard,
        )

    def _parse_inferred_blackboard(self, content: Any, blackboard: Optional[BlackboardState], name: str) -> BlackboardState:
        """
        Parses the LLM response content for inferred blackboard updates.
        Returns updated blackboard without modifying input state directly.
        """
        if not content or not isinstance(content, str):
            return blackboard or BlackboardState()

        # Support [BLACKBOARD: key=value] pattern
        # Optimized to support multi-line values and handle greedy matching more safely
        pattern = r"\[BLACKBOARD:\s*(\w+)\s*=\s*(.*?)\]"
        matches = re.findall(pattern, content, re.DOTALL)

        if matches:
            blackboard = blackboard or BlackboardState()
            metadata_updates = {}

            for key, val in matches:
                val_str = val.strip()
                if val_str.lower() == "true":
                    val = True
                elif val_str.lower() == "false":
                    val = False
                elif val_str.isdigit():
                    val = int(val_str)
                else:
                    val = val_str

                metadata_updates[key] = val
                logger.info(f"[{name}] 🖊️ Blackboard field '{key}' updated via Inference: {val}")

            blackboard.metadata = blackboard.metadata.model_copy(
                update=metadata_updates
            )

        return blackboard or BlackboardState()


_default_engine: AgentEngine | None = None


def get_default_engine() -> AgentEngine:
    """Get or create the default global AgentEngine instance."""
    global _default_engine
    if _default_engine is None:
        _default_engine = AgentEngine()
    return _default_engine


def set_default_engine(engine: AgentEngine) -> None:
    """Set the default global AgentEngine instance (for testing)."""
    global _default_engine
    _default_engine = engine
