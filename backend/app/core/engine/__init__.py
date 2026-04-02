import asyncio
import json
import logging
import re
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig

from app.constants import DEFAULT_WINDOW_SIZE, MAX_CONTEXT_CHARS
from app.core.engine.message_utils import (
    prune_redundant_results,
    repair_message_history,
    smart_window_slice,
    truncate_message_content,
)
from app.core.engine.state import AgentState
from app.core.tools.registry import get_tool_affected_paths
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.llm.factory import LLMFactory
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


class AgentEngine:
    """
    Shared execution engine for EvoLoop Agents.
    Centralizes the ReAct loop, context injection, and message repair logic.
    """

    @staticmethod
    async def run_node(
        state: AgentState,
        config: RunnableConfig,
        system_prompt: str,
        tools: list[Any],
        model: str = None,
        max_steps: int = 5,
        temperature: float = 0.7,
        name: str = "Agent",
        is_subtask: bool = False,
        node_source: str = None,  # 👈 添加节点来源标记，用于语音播报过滤
    ) -> dict[str, Any]:
        """
        Executes the standard Agent ReAct loop.

        Args:
            is_subtask: If True, uses single-shot execution (no ReAct loop).
                       Subtasks must execute tools immediately in one turn.
        """

        # 1. Initialize LLM (with instance caching for performance)
        # Get model from config if not provided directly (for model selection support)
        if model is None:
            model = config.get("configurable", {}).get("model")
        
        llm = await LLMFactory.create_llm(model_name=model, temperature=temperature)
        if tools:
            llm_with_tools = llm.bind_tools(tools)
            tool_map = {t.name: t for t in tools}
        else:
            llm_with_tools = llm
            tool_map = {}

        # 2. Config & Context
        config = AgentEngine._setup_callbacks(config)

        # 2.1 Unified Hydration (Phase 1 Optimization)
        from app.core.engine.middleware import EvoContextMiddleware
        state = await EvoContextMiddleware.hydrate(state, config)
        logger.info(f"[{name}] 🧪 Context Hydrated via Middleware")

        # 3. Message Handling & Repair
        raw_messages = list(state.get("messages", []))

        # 3.0 Context Pruning (Optional Feature)
        try:
            from app.core.memory.strategies.pruning import SmartPruningStrategy

            raw_messages = SmartPruningStrategy.prune_messages(raw_messages)
        except ImportError:
            pass

        # 3.1 Redundancy Pruning (Collapse old large outputs)
        pruned_messages = prune_redundant_results(raw_messages)

        # 3.2 Smart Windowing (Delegated to utils, with character limit)
        windowed_messages = smart_window_slice(
            pruned_messages, 
            window_size=DEFAULT_WINDOW_SIZE,
            max_total_chars=MAX_CONTEXT_CHARS 
        )

        # 3.2 Repair Orphaned Tool Messages (Delegated to utils)
        repaired_messages = repair_message_history(windowed_messages)

        # 4. Execution Mode Selection
        if is_subtask:
            # [CRITICAL FIX] Single-shot execution for subtasks
            # Eliminates loop conditions: no second turn = no repetition
            logger.info(f"[{name}] 🎯 Single-shot mode (subtask) - executing immediately")
            result = await AgentEngine._execute_single_shot(
                llm_with_tools=llm_with_tools,
                tool_map=tool_map,
                messages=repaired_messages,
                system_prompt=system_prompt,
                config=config,
                name=name,
                state=state,
            )
        else:
            # Standard ReAct loop for main tasks
            result = await AgentEngine._execute_react_loop(
                llm_with_tools=llm_with_tools,
                tool_map=tool_map,
                messages=repaired_messages,
                system_prompt=system_prompt,
                config=config,
                max_steps=max_steps,
                name=name,
                state=state,
            )
        
        # 👇 添加节点来源标记到 AI 消息
        if node_source:
            for msg in result.get("messages", []):
                if isinstance(msg, AIMessage) and msg.content:
                    if not hasattr(msg, "metadata"):
                        msg.metadata = {}
                    if msg.metadata is None:
                        msg.metadata = {}
                    msg.metadata["node_source"] = node_source
        
        return result

    @staticmethod
    def _setup_callbacks(config: RunnableConfig) -> RunnableConfig:
        """Inject TraceCallbackHandler for Imitation/Reinforcement Learning."""
        return config

    @staticmethod
    async def _execute_react_loop(
        llm_with_tools,
        tool_map: dict[str, Any],
        messages: list[BaseMessage],
        system_prompt: str,
        config: RunnableConfig,
        max_steps: int,
        name: str,
        state: dict,
    ) -> dict[str, Any]:
        """Core ReAct Loop Logic."""

        # Filter out old SystemMessages from history to avoid duplication/interleaving errors
        # (Especially critical for Anthropic which forbids multiple system messages)
        history_messages = [m for m in messages if not isinstance(m, SystemMessage)]

        # Always prepend System Prompt
        # Optimization: Inject Prompt Caching for Anthropic/Kimi
        provider = SystemConfigService.get_value("LLM_PROVIDER")
        if provider in ["anthropic", "kimi"]:
            system_msg = SystemMessage(content=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }
            ])
        else:
            system_msg = SystemMessage(content=system_prompt)

        loop_messages = [system_msg] + history_messages

        if not history_messages:
            logger.warning("[AgentEngine] No history messages (only System Prompt). Skipping LLM call to prevent API errors.")
            return {"messages": []}

        logger.debug(f"--- [AgentEngine] System Prompt ---\n{system_prompt}\n-----------------------------------------------------")

        new_messages = []
        local_tool_history = []

        for i in range(max_steps):
            logger.info(f"--- {name} Loop Step {i+1} ---")

            # Invoke LLM
            response = await llm_with_tools.ainvoke(loop_messages, config=config)

            # [Sync Fix] Inject run_id and metadata for robust rewind/cleanup
            run_id = config.get("configurable", {}).get("run_id")
            if run_id:
                if not hasattr(response, "metadata"):
                    response.metadata = {}
                response.metadata["run_id"] = run_id
                # Ensure it's also in additional_kwargs for LangChain serialization consistency
                if not hasattr(response, "additional_kwargs"):
                    response.additional_kwargs = {}
                response.additional_kwargs["run_id"] = run_id

            # OBSERVE: LLM Response (Thinking/Thought)
            thinking_content = ""
            if response.content:
                thinking_content = response.content
            elif hasattr(response, "additional_kwargs") and "thought" in response.additional_kwargs:
                thinking_content = response.additional_kwargs["thought"]

            if thinking_content:
                logger.info(f"[{name}] 🧠 Thinking: {thinking_content}")
                # --- 🏅 Inferred Blackboard Update (Phase 5 Optimization) ---
                AgentEngine._parse_inferred_blackboard(thinking_content, state, name)

            loop_messages.append(response)
            new_messages.append(response)

            if not response.tool_calls:
                logger.info(f"[{name}] 🏁 Finished with text response.")
                break

            # ★ ReAct Routing: Check for route_to tool call
            for tc in response.tool_calls:
                if tc["name"] == "route_to":
                    target = tc["args"].get("target", "finish")
                    reason = tc["args"].get("reason", "")
                    context = tc["args"].get("context", {})
                    authorized_tools = tc["args"].get("authorized_tools")

                    # Robustly handle JSON strings if passed by LLM instead of object
                    # Also handle potential double-encoding
                    while isinstance(context, str):
                        try:
                            context = json.loads(context)
                        except Exception:
                            logger.warning(f"[{name}] Failed to parse routing context JSON: {context[:100]}...")
                            context = {}
                            break

                    from app.core.engine.signals import RouteToSignal
                    logger.info(f"[{name}] 🚀 Routing Signal: → {target} ({reason})")
                    
                    # Anthropic requirement: ToolMessage follow-up
                    new_messages.append(ToolMessage(
                        content=f"Routing to {target}. Reason: {reason}",
                        tool_call_id=tc["id"],
                        name="route_to",
                        id=gen_uuid(),
                    ))

                    return {
                        "messages": new_messages,
                        "signal": RouteToSignal(
                            target=target,
                            reason=reason,
                            context=context,
                            authorized_tools=authorized_tools,
                            skill_id=tc["args"].get("skill_id")
                        )
                    }

            # ★ Phase 1: Dynamic Subtask Spawning: Check for decompose_task tool call
            from app.core.tools.executor import ToolExecutor as _ToolExecutor

            for tc in response.tool_calls:
                if tc["name"] == "decompose_task":
                    # Execute the tool to get the plan
                    tool = tool_map.get("decompose_task")
                    if tool:
                        executor = _ToolExecutor()
                        result = await executor.execute(tool, tc["args"], config=config)

                        # Check if decomposition was successful and returned a spawn plan
                        if isinstance(result, dict) and result.get("_spawn_plan"):
                            from app.core.engine.signals import SpawnSubtasksSignal
                            spawn_plan = result["_spawn_plan"]
                            logger.info(f"[{name}] 🚀 Spawn Signal: {len(spawn_plan.get('subtasks', []))} subtasks")

                            new_messages.append(ToolMessage(
                                content=f"Task decomposed into {len(spawn_plan.get('subtasks', []))} subtasks. Parallel execution triggered.",
                                tool_call_id=tc["id"],
                                name="decompose_task",
                                id=gen_uuid(),
                            ))

                            return {
                                "messages": new_messages,
                                "signal": SpawnSubtasksSignal(plan=spawn_plan)
                            }

            # Execute Tools
            # Execute Tools in Parallel (asyncio.gather)
            async def _process_single_tool(tc):
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_id = tc["id"]

                logger.info(f"[{name}] 🛠️ Call: {tool_name} | Args: {json.dumps(tool_args)}")

                # Track tool execution history and detect repetitions
                tool_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                if tool_sig in local_tool_history:
                    logger.warning(f"[{name}] ⚠️ REPETITION DETECTED: Agent is repeating tool call: {tool_sig}")
                local_tool_history.append(tool_sig)

                tool = tool_map.get(tool_name)
                executor = _ToolExecutor()

                if tool:
                    try:
                        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
                        snapshot_paths = get_tool_affected_paths(tool_name, tool_args)

                        # Capture Snapshots
                        from app.core.memory.diff import diff_tracker
                        for path in snapshot_paths:
                            diff_tracker.capture_snapshot(path, thread_id)

                        # Execute Tool
                        content = await executor.execute(tool, tool_args, config=config)

                        # --- Diff Tracking (Calculated Sync, Persisted Async) ---
                        for path in snapshot_paths:
                            try:
                                operation, diff, original_content = diff_tracker.compute_diff(path, thread_id)
                                if diff:
                                    logger.info(f"📝 Diff Detected ({operation}) on {path} (Persisting in Background)")
                                    # Offload DB Write to Celery
                                    try:
                                        from app.infrastructure.queue.celery import celery_app
                                        msg_id = config.get("configurable", {}).get("run_id") or tool_id
                                        celery_app.send_task(
                                            "engine_persist_file_operation",
                                            kwargs={
                                                "thread_id": thread_id,
                                                "message_id": str(msg_id),
                                                "file_path": path,
                                                "operation": operation,
                                                "diff_content": diff,
                                                "original_content": original_content,
                                            }
                                        )
                                    except Exception:
                                        logger.warning("Failed to dispatch FileOperation to Celery.")
                            except Exception as e:
                                logger.error(f"Failed to process diff for {path}: {e}")

                    except Exception as e:
                        content = f"Error executing {tool_name}: {e}"
                else:
                    content = f"Error: Tool {tool_name} not found."

                # [Sync Fix] Inject run_id for robust rewind
                run_id = config.get("configurable", {}).get("run_id")
                metadata = {"run_id": run_id} if run_id else {}

                return ToolMessage(
                    content=truncate_message_content(str(content)),
                    tool_call_id=tool_id,
                    name=tool_name,
                    id=gen_uuid(),
                    metadata=metadata,
                    additional_kwargs=metadata
                )

            # Gather all tool results for this step
            tool_results = await asyncio.gather(*[_process_single_tool(tc) for tc in response.tool_calls])

            for tool_msg in tool_results:
                logger.info(f"[{name}] ✅ Result ({tool_msg.name}): {str(tool_msg.content[:500])}...")
                loop_messages.append(tool_msg)
                new_messages.append(tool_msg)

                # --- 🏅 Cognitive Evolution Path: Signal Handling ---
                # Check for structured signals in tool messages
                content_raw = tool_msg.content
                signal_data = None
                
                try:
                    # Attempt to parse as JSON if it's a string from a tool
                    if isinstance(content_raw, str) and (content_raw.startswith("{") or content_raw.startswith("[")):
                        signal_data = json.loads(content_raw)
                    elif isinstance(content_raw, dict):
                        signal_data = content_raw
                except Exception:
                    pass

                if isinstance(signal_data, dict) and "_signal" in signal_data:
                    sig_type = signal_data["_signal"]
                    sig_payload = signal_data.get("data", {})
                    
                    # 1. Session Metadata Signal
                    if sig_type == "update_session_metadata":
                        key = sig_payload.get("key")
                        val = sig_payload.get("value")
                        if key:
                            blackboard = state.get("blackboard", {})
                            if "metadata" not in blackboard:
                                blackboard["metadata"] = {}
                            blackboard["metadata"][key] = val
                            logger.info(f"[{name}] 🧬 Session Metadata Updated via Signal: {key}={val}")

                # 2. History Compression Signal (Formalized)
                if "COMPRESSION_SIGNAL|" in str(tool_msg.content):
                    try:
                        from langchain_core.messages import RemoveMessage
                        # To keep context light, we remove everything except the last 3 messages 
                        # and the very first human message (intent).
                        # Note: We emit RemoveMessage objects which 'add_messages' in AgentState will process.
                        to_remove = []
                        # messages in state
                        all_messages = state.get("messages", [])
                        if len(all_messages) > 10:
                            # Keep first message (User Intent)
                            # Remove others up to the last 5
                            for m in all_messages[1:-5]:
                                if hasattr(m, "id") and m.id:
                                    to_remove.append(RemoveMessage(id=m.id))
                            
                            if to_remove:
                                logger.info(f"[{name}] 🧹 History Compression Triggered: Removing {len(to_remove)} messages")
                                new_messages.extend(to_remove)
                    except Exception as e:
                        logger.warning(f"[{name}] Failed to execute history compression: {e}")

        # Loop ended (e.g., hit max_steps without returning)
        if len(new_messages) > 0 and len(response.tool_calls) > 0:
            logger.error(f"[{name}] 🔴 Hit max_steps ({max_steps}) with open tool calls. Forcing termination.")
            # Phase 4 Autonomy: Provide a clear signal that it was forcefully truncated
            truncation_msg = AIMessage(
                content="Execution reached maximum step limit and was paused."
            )
            new_messages.append(truncation_msg)

        return {
            "messages": new_messages,
            "tool_history": local_tool_history,
            "blackboard": state.get("blackboard"),
        }

    @staticmethod
    async def _execute_single_shot(
        llm_with_tools,
        tool_map: dict[str, Any],
        messages: list[BaseMessage],
        system_prompt: str,
        config: RunnableConfig,
        name: str,
        state: dict,
    ) -> dict[str, Any]:
        """
        Single-shot execution for subtasks.

        CORE PRINCIPLE: Eliminate loop conditions by physically preventing a second turn.
        No second turn = no opportunity for repetitive thinking.

        Rules:
        1. ONE LLM call only
        2. MUST call at least one tool (subtasks are for action, not chitchat)
        3. Execute tools immediately
        4. Return results - no second LLM turn for "analysis" or "confirmation"
        """
        from app.core.tools.executor import ToolExecutor as _ToolExecutor

        # Prepare messages (filter out old system messages)
        history_messages = [m for m in messages if not isinstance(m, SystemMessage)]
        system_msg = SystemMessage(content=system_prompt)
        loop_messages = [system_msg] + history_messages

        if not history_messages:
            logger.warning(f"[{name}] No history messages for single-shot. Skipping.")
            return {"messages": [], "tool_history": [], "blackboard": state.get("blackboard")}

        logger.info(f"[{name}] 🎯 SINGLE-SHOT: Executing immediate tool call...")

        # Single LLM invocation
        try:
            response = await llm_with_tools.ainvoke(loop_messages, config=config)
        except Exception as e:
            logger.error(f"[{name}] Single-shot LLM invocation failed: {e}")
            return {
                "messages": [AIMessage(content="Failed to invoke LLM due to system error.")],
                "tool_history": [],
                "blackboard": state.get("blackboard"),
            }

        # Inject run_id for tracking
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

        # --- 🏅 Inferred Blackboard Update (Phase 5 Optimization) ---
        AgentEngine._parse_inferred_blackboard(response.content, state, name)

        # CRITICAL: Subtask MUST call tools
        if not response.tool_calls:
            logger.error(f"[{name}] 🛑 SINGLE-SHOT VIOLATION: Subtask did not call any tool!")
            error_msg = AIMessage(
                content="Subtask failed: No tool was invoked.")
            new_messages.append(error_msg)
            return {
                "messages": new_messages,
                "tool_history": local_tool_history,
                "blackboard": state.get("blackboard"),
                "_routing_target": None,
            }

        # Execute all tools in parallel
        logger.info(f"[{name}] 🛠️ Executing {len(response.tool_calls)} tool(s) immediately...")

        async def _execute_tool(tc: dict) -> ToolMessage:
            tool_name = tc["name"]
            tool_args = tc["args"]
            tool_id = tc["id"]

            tool_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
            local_tool_history.append(tool_sig)

            tool = tool_map.get(tool_name)
            executor = _ToolExecutor()

            if not tool:
                content = f"Error: Tool {tool_name} not found."
            else:
                try:
                    content = await executor.execute(tool, tool_args, config=config)
                except Exception as e:
                    content = f"Error executing {tool_name}: {e}"

            # Inject run_id
            metadata = {"run_id": run_id} if run_id else {}

            return ToolMessage(
                content=truncate_message_content(str(content)),
                tool_call_id=tool_id,
                name=tool_name,
                id=gen_uuid(),
                metadata=metadata,
                additional_kwargs=metadata
            )

        # Execute all tools concurrently
        tool_results = await asyncio.gather(*[_execute_tool(tc) for tc in response.tool_calls])

        for tool_msg in tool_results:
            logger.info(f"[{name}] ✅ Result ({tool_msg.name}): {str(tool_msg.content[:500])}...")
            new_messages.append(tool_msg)

        # IMMEDIATE TERMINATION: No second LLM turn
        # Results go directly to parent - no "analysis" or "confirmation" phase
        logger.info(f"[{name}] ✓ Single-shot complete. {len(response.tool_calls)} tool(s) executed.")

        return {
            "messages": new_messages,
            "tool_history": local_tool_history,
            "blackboard": state.get("blackboard"),
            "_routing_target": None,
        }

    @staticmethod
    def _parse_inferred_blackboard(content: Any, state: dict, name: str):
        """
        Parses the LLM response content for inferred blackboard updates.
        Pattern: [BLACKBOARD: key=value]
        """
        if not content or not isinstance(content, str):
            return

        # Support [BLACKBOARD: key=value] pattern
        pattern = r"\[BLACKBOARD:\s*(\w+)\s*=\s*(.*?)\]"
        matches = re.findall(pattern, content)

        if matches:
            blackboard = state.get("blackboard") or {}
            metadata = blackboard.get("metadata", {})

            for key, val in matches:
                # Basic type inference
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

            blackboard["metadata"] = metadata
            state["blackboard"] = blackboard
