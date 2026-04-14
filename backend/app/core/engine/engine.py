"""
AgentEngine - Instance-based execution engine for EvoLoop Agents.

This module provides the main AgentEngine class as an instance-based
alternative to the static methods. Supports dependency injection for
easier testing and extensibility.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from pydantic import Field

from app.constants import (
    DEFAULT_CONTEXT_LIMIT,
    DEFAULT_WINDOW_SIZE,
    NODE_WINDOW_SIZES,
)
from app.core.engine.message_utils import (
    apply_forgotten_status,
    repair_message_history,
    smart_window_slice,
)
from app.core.engine.state import AgentState, BlackboardState
from app.core.engine.tool_executor import AgentToolExecutor
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
    blackboard: Any = None
    is_truncated: bool = False
    signal: Any = None
    _routing_target: str | None = None


class AgentEngine:
    """
    Instance-based execution engine for EvoLoop Agents.

    Supports dependency injection for easier testing and extensibility.

    Example:
        # Using default dependencies
        engine = AgentEngine()
        result = await engine.run_node(state, config, system_prompt, tools)

        # With custom dependencies (for testing)
        engine = AgentEngine(
            llm_factory=mock_llm_factory,
            config_service=mock_config_service,
        )
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
        """
        Executes the standard Agent ReAct loop.

        Args:
            is_subtask: If True, uses single-shot execution (no ReAct loop).
                       Subtasks must execute tools immediately in one turn.
        """
        # 1. Initialize LLM (with instance caching for performance)
        if model is None:
            model = config.get("configurable", {}).get("model")

        llm = await self._llm_factory.create_llm(model_name=model, temperature=temperature)

        # 1.1 Detect Provider for Prompt Caching
        provider = "openai"
        try:
            # Check class name or specific adapter types
            class_name = llm.__class__.__name__
            if "Anthropic" in class_name:
                provider = "anthropic"
            elif hasattr(llm, "lc_secrets") and "anthropic" in str(llm.lc_secrets).lower():
                provider = "anthropic"
        except Exception:
            pass

        if tools:
            llm_with_tools = llm.bind_tools(tools)
            tool_map = {t.name: t for t in tools}
        else:
            llm_with_tools = llm
            tool_map = {}

        # 2. Config & Context
        config = self._setup_callbacks(config)

        # 2.1 Unified Hydration (Phase 1 Optimization)
        from app.core.engine.context_hydrator import EvoContextMiddleware
        state = await EvoContextMiddleware.hydrate(state, config)
        logger.info(f"[{name}] 🧪 Context Hydrated via Middleware")

        # 3. Message Handling & Repair
        raw_messages = list(list(state.messages))
        logger.info(f"[{name}] 📨 Raw messages: {len(raw_messages)} | Types: {[type(m).__name__ for m in raw_messages]}")

        # 3.0 Context Pruning removed - Agent-controlled forgetting replaces it

        # 3.1 Apply Agent-Controlled Forgetting
        tool_memory = get_tool_memory_from_state(state)
        messages_with_forgetting = apply_forgotten_status(raw_messages, tool_memory)
        logger.info(f"[{name}] 🧠 After forgetting: {len(messages_with_forgetting)} messages")

        # 3.2 Hierarchical Smart Windowing
        ctx_config = config.get("configurable", {})
        effective_window = NODE_WINDOW_SIZES.get(node_source, DEFAULT_WINDOW_SIZE)

        windowed_messages = await smart_window_slice(
            messages_with_forgetting,
            window_size=effective_window,
            max_total_chars=DEFAULT_CONTEXT_LIMIT,
            model=model,
            node_source=node_source or "default",
            thread_id=ctx_config.get("thread_id"),
            user_id=ctx_config.get("user_id"),
            project_id=ctx_config.get("project_id"),
        )

        logger.info(
            f"[{name}] 📐 Window: {len(messages_with_forgetting)} -> {len(windowed_messages)} messages "
            f"(forgotten: {len(tool_memory.forgotten)}, node={node_source}, window={effective_window})"
        )

        # 3.2 Repair Orphaned Tool Messages
        repaired_messages = repair_message_history(windowed_messages)
        logger.info(f"[{name}] 🔧 After repair: {len(repaired_messages)} messages | Types: {[type(m).__name__ for m in repaired_messages]}")

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
                max_steps=max_steps,
                name=name,
                state=state,
                parallel_tools=parallel_tools,
            )

        # Add node_source marker to AI messages
        if node_source:
            for msg in result.messages or []:
                if isinstance(msg, AIMessage) and msg.content:
                    if not hasattr(msg, "metadata"):
                        msg.metadata = {}
                    if msg.metadata is None:
                        msg.metadata = {}
                    msg.metadata["node_source"] = node_source

        return result

    def _setup_callbacks(self, config: RunnableConfig) -> RunnableConfig:
        """Inject TraceCallbackHandler for Imitation/Reinforcement Learning."""
        return config

    async def _execute_react_loop(
        self,
        llm_with_tools,
        tool_map: dict[str, Any],
        messages: list[BaseMessage],
        system_prompt: str,
        provider: str, # Added provider
        config: RunnableConfig,
        name: str,
        state: AgentState,
        max_steps: int = 5,
        parallel_tools: bool = False,
    ) -> EngineResult:
        """Core ReAct Loop Logic."""
        # 0. Build optimized system messages for Prompt Caching
        system_messages = self._build_system_messages(system_prompt, messages, provider)

        # 1. Separate context ticket and history messages
        # Standard ReAct: System + History
        history_messages = [m for m in messages if not isinstance(m, SystemMessage)]

        loop_messages = system_messages + history_messages

        if not history_messages:
            logger.error(f"[{name}] 🔴 No history messages! Returning empty.")
            return EngineResult(messages=[])

        new_messages = []
        local_tool_history = []
        last_response = None

        for i in range(max_steps):
            # Check for cancellation
            thread_id = config.get("configurable", {}).get("thread_id")
            if thread_id:
                await activity_monitor.check_cancellation(thread_id)

            logger.info(f"--- {name} Loop Step {i+1} ---")

            # Invoke LLM
            try:
                start_perf = time.perf_counter()
                response = await llm_with_tools.ainvoke(loop_messages, config=config)
                latency = time.perf_counter() - start_perf

                # Update log with success
                try:
                    with open("tests/monitoring/audit_evidence.log", "a") as f:
                        f.write(f"TURN_POST_CALL: {name} | Success | Latency: {latency:.2f}s\n")
                        f.flush()
                        os.fsync(f.fileno())
                except Exception:
                    pass

                # [TELEMETRY] Record inference
                agent_telemetry.record_inference(
                    node_name=name,
                    turn_id=i,
                    prompt_info={
                        "system_len": len(system_prompt),
                        "history_len": sum(len(str(m.content)) for m in history_messages),
                        "total_len": len(system_prompt) + sum(len(str(m.content)) for m in loop_messages)
                    },
                    response_info={
                        "content": response.content,
                        "usage": getattr(response, "usage_metadata", {}),
                        "is_tool_call": bool(response.tool_calls),
                        "tool_names": [tc["name"] for tc in response.tool_calls]
                    },
                    latency_ms=latency * 1000,
                    metadata={"max_steps": max_steps, "parallel_tools": parallel_tools}
                )

                last_response = response
            except Exception as e:
                return self._handle_llm_exception(e, name, state)

            # Inject run_id
            run_id = config.get("configurable", {}).get("run_id")
            if run_id:
                if not hasattr(response, "metadata"):
                    response.metadata = {}
                response.metadata["run_id"] = run_id
                if not hasattr(response, "additional_kwargs"):
                    response.additional_kwargs = {}
                response.additional_kwargs["run_id"] = run_id

            # Parse thinking content
            thinking_content = ""
            content_preview = str(response.content)[:200] if response.content else "(empty)"
            tool_calls_count = len(response.tool_calls) if hasattr(response, 'tool_calls') and response.tool_calls else 0
            logger.info(f"[{name}] 📥 LLM response: content='{content_preview}...', tool_calls={tool_calls_count}")

            if response.content:
                thinking_content = response.content
            elif hasattr(response, "additional_kwargs") and "thought" in response.additional_kwargs:
                thinking_content = response.additional_kwargs["thought"]
                logger.info(f"[{name}] 🧠 Thinking (from additional_kwargs): {thinking_content[:200]}...")

            if thinking_content:
                logger.info(f"[{name}] 🧠 Thinking: {thinking_content}")
                state.blackboard = self._parse_inferred_blackboard(
                    thinking_content, state.blackboard, name
                )

            loop_messages.append(response)
            new_messages.append(response)

            if not response.tool_calls:
                logger.info(f"[{name}] 🏁 Finished with text response (no tool calls).")
                break

            from app.core.callbacks.transparent import TransparentCallbackHandler
            from app.core.engine.signals import RouteToSignal, SpawnSubtasksSignal
            from app.core.tools.executor import ToolExecutor as _ToolExecutor

            # Turn-level signal tracking
            pending_signal = None

            # Extract TransparentCallbackHandler to restore observability for intercepted tools
            evoloop_handler = None
            callbacks = config.get("callbacks", []) if config else []
            callback_list = callbacks if isinstance(callbacks, list) else getattr(callbacks, "handlers", [])
            for cb in callback_list:
                if isinstance(cb, TransparentCallbackHandler):
                    evoloop_handler = cb
                    break

            for tc in response.tool_calls:
                # Skip if we already have a pending signal (only one signal per turn allowed)
                if pending_signal is not None:
                    logger.warning(f"[{name}] ⚠️ Multiple signals detected in one turn. Ignoring additional signal: {tc['name']}")
                    continue

                # 1. Check for route_to signal
                if tc["name"] == "route_to":
                    if evoloop_handler:
                        try:
                            await evoloop_handler.on_tool_start(
                                serialized={"name": "route_to"},
                                input_str=json.dumps(tc["args"], ensure_ascii=False),
                                run_id=tc["id"]
                            )
                        except Exception as e:
                            logger.error(f"Failed to log intercepted tool start: {e}")

                    target = tc["args"].get("target", "finish")
                    reason = tc["args"].get("reason", "")
                    context = tc["args"].get("context", {})
                    authorized_tools = tc["args"].get("authorized_tools")

                    if isinstance(context, str):
                        try:
                            context = json.loads(context)
                        except Exception:
                            context = {}

                    logger.info(f"[{name}] 🚀 Intent: → {target} ({reason})")
                    pending_signal = RouteToSignal(
                        target=target,
                        reason=reason,
                        context=context,
                        authorized_tools=authorized_tools,
                        skill_id=tc["args"].get("skill_id")
                    )

                    output_msg = f"Routing to {target}"
                    # Add ToolMessage for route_to to satisfy protocol (every tool_call needs a response)
                    new_messages.append(ToolMessage(
                        content=output_msg,
                        tool_call_id=tc["id"],
                        name="route_to",
                        id=gen_uuid(),
                    ))

                    if evoloop_handler:
                        try:
                            await evoloop_handler.on_tool_end(output=output_msg, run_id=tc["id"])
                        except Exception as e:
                            logger.error(f"Failed to log intercepted tool end: {e}")

                # 2. Check for decompose_task signal
                elif tc["name"] == "decompose_task":
                    tool = tool_map.get("decompose_task")
                    if tool:
                        executor = _ToolExecutor()
                        result = await executor.execute(tool, tc["args"], config=config)

                        if isinstance(result, dict) and result.get("_spawn_plan"):
                            from app.core.engine.state.blackboard import SpawnPlan
                            spawn_plan = SpawnPlan.model_validate(result["_spawn_plan"])
                            logger.info(f"[{name}] 🚀 Intent: Spawn {len(spawn_plan.subtasks or [])} subtasks")

                            new_messages.append(ToolMessage(
                                content=f"Task decomposed into {len(spawn_plan.subtasks or [])} subtasks.",
                                tool_call_id=tc["id"],
                                name="decompose_task",
                                id=gen_uuid(),
                            ))
                            pending_signal = SpawnSubtasksSignal(plan=spawn_plan)

            # 3. Execute Non-Signal Tools
            remaining_tool_calls = [tc for tc in response.tool_calls if tc["name"] not in ("route_to", "decompose_task")]

            if remaining_tool_calls:
                tool_executor = self._tool_executor_class(
                    tool_map=tool_map,
                    state=state,
                    config=config,
                    name=name,
                    enable_diff_tracking=self._enable_diff_tracking,
                )

                async def _process_single_tool(tc):
                    return await tool_executor.execute_tool(
                        tool_name=tc["name"],
                        tool_args=tc["args"],
                        tool_id=tc["id"],
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

                for tool_msg in tool_results:
                    logger.info(f"[{name}] ✅ Result ({tool_msg.name}): {str(tool_msg.content[:300])}...")
                    loop_messages.append(tool_msg)
                    new_messages.append(tool_msg)

            # 4. Dispatch Signal if present after tool execution
            if pending_signal:
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
        name: str,
        state: AgentState,
        parallel_tools: bool = False,
    ) -> dict[str, Any]:
        """Single-shot execution for subtasks."""
        # Build optimized system messages for Prompt Caching
        system_messages = self._build_system_messages(system_prompt, messages, provider)
        history_messages = [m for m in messages if not isinstance(m, SystemMessage)]

        loop_messages = system_messages + history_messages

        if not history_messages:
            logger.error(f"[{name}] 🔴 No history messages! Returning empty.")
            return EngineResult(messages=[])

        # [DIAGNOSTIC] Capture System Prompt stability and Latency
        sys_hash = hashlib.md5(system_prompt.encode()).hexdigest()
        start_perf = time.perf_counter()
        try:
            response = await llm_with_tools.ainvoke(loop_messages, config=config)
            latency = time.perf_counter() - start_perf

            try:
                with open("tests/monitoring/audit_evidence.log", "a") as f:
                    f.write(f"TURN_MARKER: {name}_subtask | Hash: {sys_hash} | Latency: {latency:.2f}s | Length: {len(system_prompt)}\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception:
                pass

            logger.warning(f"[{name}] 🧩 PROMPT CACHE DIAGNOSTIC: SystemPromptHash={sys_hash} | Latency={latency:.2f}s")

            # [TELEMETRY] Record inference
            agent_telemetry.record_inference(
                node_name=f"{name}_subtask",
                turn_id=0,
                prompt_info={
                    "system_len": len(system_prompt),
                    "history_len": sum(len(str(m.content)) for m in history_messages),
                    "total_len": len(system_prompt) + sum(len(str(m.content)) for m in loop_messages)
                },
                response_info={
                    "content": response.content,
                    "usage": getattr(response, "usage_metadata", {}),
                    "is_tool_call": bool(response.tool_calls),
                    "tool_names": [tc["name"] for tc in response.tool_calls]
                },
                latency_ms=latency * 1000,
                metadata={"is_single_shot": True}
            )
        except Exception as e:
            return self._handle_llm_exception(e, name, state)

        # Inject run_id
        run_id = config.get("configurable", {}).get("run_id")
        if run_id:
            if not hasattr(response, "metadata"):
                response.metadata = {}
            response.metadata["run_id"] = run_id
            if not hasattr(response, "additional_kwargs"):
                response.additional_kwargs = {}
            response.additional_kwargs["run_id"] = run_id

        new_messages = [response]
        local_tool_history = []

        # Parse blackboard
        state.blackboard = self._parse_inferred_blackboard(
            response.content, state.blackboard, name
        )

        # CRITICAL: Subtask MUST call tools
        if not response.tool_calls:
            logger.error(f"[{name}] 🛑 SINGLE-SHOT VIOLATION: Subtask did not call any tool!")
            error_msg = AIMessage(content="Subtask failed: No tool was invoked.")
            new_messages.append(error_msg)
            return EngineResult(
                messages=new_messages,
                tool_history=local_tool_history,
                blackboard=state.blackboard,
                _routing_target=None,
            )

        # 3. Execute Non-Signal Tools
        remaining_tool_calls = [tc for tc in response.tool_calls if tc["name"] not in ("route_to", "decompose_task")]

        if remaining_tool_calls:
            # Execute Tools using shared AgentToolExecutor
            tool_executor = self._tool_executor_class(
                tool_map=tool_map,
                state=state,
                config=config,
                name=name,
                enable_diff_tracking=self._enable_diff_tracking,
            )

            async def _execute_tool(tc: dict) -> ToolMessage:
                return await tool_executor.execute_tool(
                    tool_name=tc["name"],
                    tool_args=tc["args"],
                    tool_id=tc["id"],
                    local_tool_history=local_tool_history,
                )

            # Execute tools (Single-shot subtasks often call multiple independent tools)
            if parallel_tools:
                logger.info(f"[{name}] ⚡ Executing {len(remaining_tool_calls)} tools in parallel")
                tool_results = await asyncio.gather(*[_execute_tool(tc) for tc in remaining_tool_calls])
            else:
                logger.info(f"[{name}] ⛓️ Executing {len(remaining_tool_calls)} tools sequentially")
                tool_results = []
                for tc in remaining_tool_calls:
                    res = await _execute_tool(tc)
                    tool_results.append(res)

            for tool_msg in tool_results:
                logger.info(f"[{name}] ✅ Result ({tool_msg.name}): {str(tool_msg.content[:300])}...")
                new_messages.append(tool_msg)

        logger.info(f"[{name}] ✓ Single-shot complete. {len(response.tool_calls)} tool(s) executed.")

        return EngineResult(
            messages=new_messages,
            tool_history=local_tool_history,
            blackboard=state.blackboard,
            _routing_target=None,
        )

    def _build_system_messages(self, system_prompt: str, messages: list, provider: str) -> list[BaseMessage]:
        """
        Builds system messages optimized for Prompt Caching.
        Decouples static instructions from dynamic telemetry to maximize cache hit rates.
        """
        # 2. Provider-specific optimization
        # Use nested list structure (Anthropic format) ONLY for pure anthropic providers.
        # For Kimi (routing via OpenAI gateway) or others, use standard string content.
        # Caching on OpenAI-compatible providers is usually achieved by keeping the prefix static.
        if provider == "anthropic":
            return [SystemMessage(content=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }
            ])]
        else:
            # Standard string content for Moonshot/Kimi/DeepSeek/OpenAI
            return [SystemMessage(content=system_prompt)]

    def _handle_llm_exception(self, e: Exception, name: str, state: AgentState) -> EngineResult:
        """Centralized handling for LLM invocation exceptions."""
        import openai

        logger.error(f"[{name}] LLM invocation failed: {e}")

        error_str = str(e).lower()
        error_type = "llm_invocation_system"
        status_code = None

        # [CRITICAL] Check for EvoLoop platform auth errors first
        # These are raised as ValueError, not OpenAIError
        if "not authenticated with evoloop" in error_str or "please login first" in error_str:
            error_type = "auth_expired"
            status_code = 401
            logger.warning(f"[{name}] EvoLoop platform authentication expired")

        elif isinstance(e, openai.OpenAIError):
            if hasattr(e, "status_code"):
                status_code = e.status_code

        if error_type != "auth_expired":
            if status_code == 401 or "unauthorized" in error_str or "auth" in error_str:
                error_type = "llm_auth"
                status_code = 401
            elif status_code == 403:
                if "quota" in error_str or "usage limit" in error_str or "billing" in error_str:
                    error_type = "quota_exhausted"
                else:
                    error_type = "llm_auth"
            elif status_code == 429 or "rate limit" in error_str or "too many requests" in error_str:
                error_type = "rate_limit"
                status_code = 429
        elif status_code in (500, 502, 503, 504) or any(kw in error_str for kw in ("unavailable", "overloaded", "gateway", "service error")):
            error_type = "service_unavailable"
            status_code = status_code or 503
        elif any(kw in error_str for kw in ("timeout", "connection", "socket", "network")):
            error_type = "network_error"
        elif "model_not_found" in error_str or "not found" in error_str:
            error_type = "invalid_config"
            status_code = 404

        # Return error message as AIMessage - this is a terminal error (LLM failed)
        # The context_hydrator will clean up accumulated errors on retry
        # NOTE: Unlike Supervisor protocol errors, LLM errors ARE valid terminal states
        # that should be visible to the user (e.g., "API quota exceeded")
        user_friendly_msg = self._get_user_friendly_error(error_type, str(e))
        return EngineResult(
            messages=[AIMessage(
                content=user_friendly_msg,
                metadata={
                    "is_error": True,
                    "error_type": error_type,
                    "status_code": status_code,
                    "raw_error": str(e)
                }
            )],
            tool_history=[],
            blackboard=state.blackboard,
        )

    def _get_user_friendly_error(self, error_type: str, raw_error: str) -> str:
        """Convert technical errors to user-friendly messages."""
        from app.i18n.service import i18n

        error_messages = {
            "llm_auth": i18n.get("errors.llm_auth", default="Authentication failed. Please check your API key configuration."),
            "auth_expired": i18n.get("errors.auth_expired", default="EvoLoop session expired. Please login again to continue."),
            "quota_exhausted": i18n.get("errors.quota_exhausted", default="API quota exhausted. Please try again later or contact support."),
            "rate_limit": i18n.get("errors.rate_limit", default="Request rate limit reached. Please wait a moment and try again."),
            "service_unavailable": i18n.get("errors.service_unavailable", default="AI service is temporarily unavailable. Please try again in a moment."),
            "network_error": i18n.get("errors.network_error", default="Network connection issue. Please check your internet connection."),
            "invalid_config": i18n.get("errors.invalid_config", default="Invalid AI model configuration. Please check your settings."),
        }
        return error_messages.get(error_type, i18n.get("errors.llm_generic", default="An error occurred while processing your request. Please try again."))

    def _parse_inferred_blackboard(self, content: Any, blackboard: Optional["BlackboardState"], name: str) -> Optional["BlackboardState"]:
        """
        Parses the LLM response content for inferred blackboard updates.
        Returns updated blackboard without modifying input state directly.
        """
        if not content or not isinstance(content, str):
            return blackboard

        # Support [BLACKBOARD: key=value] pattern
        # Optimized to support multi-line values and handle greedy matching more safely
        pattern = r"\[BLACKBOARD:\s*(\w+)\s*=\s*(.*?)\]"
        matches = re.findall(pattern, content, re.DOTALL)

        if matches:
            from app.core.engine.state.blackboard import (
                BlackboardMetadata,
                BlackboardState,
            )
            if not isinstance(blackboard, BlackboardState):
                blackboard = BlackboardState.model_validate(blackboard) if blackboard else BlackboardState()
            metadata = dict(blackboard.metadata) if blackboard.metadata else {}

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

                metadata[key] = val
                logger.info(f"[{name}] 🖊️ Blackboard field '{key}' updated via Inference: {val}")

            blackboard.metadata = BlackboardMetadata.model_validate(metadata)

        return blackboard


# Global default instance for backward compatibility
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
