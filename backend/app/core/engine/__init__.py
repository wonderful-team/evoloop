import asyncio
import json
import logging
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig

from app.core.engine.message_utils import (
    repair_message_history,
    smart_window_slice,
    truncate_message_content,
)
from app.core.engine.state import AgentState
from app.core.tools.registry import is_state_mutating_tool, is_pollable_tool, get_tool_affected_paths
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
    ) -> dict[str, Any]:
        """
        Executes the standard Agent ReAct loop.
        """

        # 1. Initialize LLM
        llm = LLMFactory.create_llm(model_name=model, temperature=temperature)
        if tools:
            llm_with_tools = llm.bind_tools(tools)
            tool_map = {t.name: t for t in tools}
        else:
            llm_with_tools = llm
            tool_map = {}

        # 2. Config & Context
        config = AgentEngine._setup_callbacks(config)

        # 2.1 Hydrate ContextManager
        from app.core.context import ContextManager, EvoContext
        ctx = ContextManager.current()

        # Only hydrate if the context is the global fallback (meaning ContextVar is lost)
        # We must respect project_id=0 (Global Mode) if it is explicitly in state/config
        if ctx.request_id == "global-fallback":
            project_id = state.get("project_id")
            if project_id is None:
                project_id = config.get("configurable", {}).get("project_id", 1)

            working_directory = state.get("scratchpad", {}).get("working_directory") or config.get("configurable", {}).get("working_directory")

            new_ctx = EvoContext(
                project_id=project_id,
                working_directory=working_directory,
                thread_id=config.get("configurable", {}).get("thread_id"),
                request_id=f"run-{gen_uuid()[:8]}"
            )
            ContextManager.set(new_ctx)
            logger.info(f"[{name}] 🧪 Context Hydrated: project_id={project_id}, wd={working_directory}")

        # 3. Message Handling & Repair
        raw_messages = list(state.get("messages", []))

        # 3.0 Context Pruning (Optional Feature)
        try:
            from app.core.memory.strategies.pruning import SmartPruningStrategy

            raw_messages = SmartPruningStrategy.prune_messages(raw_messages)
        except ImportError:
            pass

        # 3.1 Smart Windowing (Delegated to utils)
        windowed_messages = smart_window_slice(raw_messages, window_size=30)

        # 3.2 Repair Orphaned Tool Messages (Delegated to utils)
        repaired_messages = repair_message_history(windowed_messages)

        # 4. Loop Execution
        return await AgentEngine._execute_react_loop(
            llm_with_tools=llm_with_tools,
            tool_map=tool_map,
            messages=repaired_messages,
            system_prompt=system_prompt,
            config=config,
            max_steps=max_steps,
            name=name,
        )

    @staticmethod
    def _setup_callbacks(config: RunnableConfig) -> RunnableConfig:
        """Inject TraceCallbackHandler for Imitation/Reinforcement Learning."""
        try:
            from app.core.learning.trace_recorder import TraceCallbackHandler

            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            if thread_id and thread_id != "unknown":
                trace_handler = TraceCallbackHandler(thread_id)

                # Safely update callbacks
                existing_callbacks = config.get("callbacks", []) or []
                if not isinstance(existing_callbacks, list):
                    if hasattr(existing_callbacks, "handlers"):
                        existing_callbacks = existing_callbacks.handlers
                    else:
                        existing_callbacks = [existing_callbacks]

                # Check duplication
                has_tracer = any(isinstance(c, TraceCallbackHandler) for c in existing_callbacks)

                if not has_tracer:
                    config = config.copy()
                    config["callbacks"] = existing_callbacks + [trace_handler]
        except Exception as e:
            logger.warning(f"Failed to inject TraceCallbackHandler: {e}")

        return config

    @staticmethod
    def _inject_system_context(system_prompt: str) -> str:
        """Inject language preference if missing."""
        user_lang = SystemConfigService.get_language_preference()
        if "User Language Preference:" not in system_prompt:
            return system_prompt + f"\n\nUser Language Preference: {user_lang}\nCommunicate in this language."
        return system_prompt

    @staticmethod
    async def _execute_react_loop(
        llm_with_tools,
        tool_map: dict[str, Any],
        messages: list[BaseMessage],
        system_prompt: str,
        config: RunnableConfig,
        max_steps: int,
        name: str,
    ) -> dict[str, Any]:
        """Core ReAct Loop Logic."""

        # Filter out old SystemMessages from history to avoid duplication/interleaving errors
        # (Especially critical for Anthropic which forbids multiple system messages)
        history_messages = [m for m in messages if not isinstance(m, SystemMessage)]

        # Always prepend System Prompt
        # Optimization: Inject Prompt Caching for Anthropic if provider is set
        if SystemConfigService.get_value("LLM_PROVIDER") == "anthropic":
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
            logger.info(f"--- {name} Loop Step {i + 1} ---")

            # Invoke LLM
            response = await llm_with_tools.ainvoke(loop_messages, config=config)

            # OBSERVE: LLM Response (Thinking)
            if response.content:
                logger.info(f"[{name}] 🧠 Thinking: {response.content}")

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

                    logger.info(f"[{name}] 🚀 Routing Signal: → {target} ({reason}) | Auth: {len(authorized_tools) if isinstance(authorized_tools, list) else 'None'}")
                    
                    # 🏅 Fix: Anthropic requirement - Every tool call MUST be followed by a ToolMessage
                    # We add the ToolMessage to new_messages so it persists in state
                    routing_tool_msg = ToolMessage(
                        content=f"Routing to {target}. Reason: {reason}",
                        tool_call_id=tc["id"],
                        name="route_to",
                        id=gen_uuid(),
                    )
                    new_messages.append(routing_tool_msg)

                    # Return immediately with routing information
                    return {
                        "messages": new_messages,
                        "_routing_target": target,
                        "_routing_reason": reason,
                        "_routing_context": context,
                        "_authorized_tools": authorized_tools,
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
                            spawn_plan = result["_spawn_plan"]
                            logger.info(f"[{name}] 🚀 Spawn Signal: {len(spawn_plan.get('subtasks', []))} subtasks")

                            # 🏅 Fix: Add ToolMessage for decompose_task to satisfy LLM sequence requirement
                            spawn_tool_msg = ToolMessage(
                                content=f"Task decomposed into {len(spawn_plan.get('subtasks', []))} subtasks. Executing in parallel...",
                                tool_call_id=tc["id"],
                                name="decompose_task",
                                id=gen_uuid(),
                            )
                            new_messages.append(spawn_tool_msg)

                            return {
                                "messages": new_messages,
                                "_routing_target": "spawn_subtasks",
                                "_spawn_plan": spawn_plan,
                            }

            # Execute Tools
            # Execute Tools in Parallel (asyncio.gather)
            async def _process_single_tool(tc):
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_id = tc["id"]

                logger.info(f"[{name}] 🛠️ Call: {tool_name} | Args: {json.dumps(tool_args)}")

                # Check duplication
                tool_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"

                if tool_sig in local_tool_history and not is_state_mutating_tool(tool_name) and not is_pollable_tool(tool_name):
                    content = f"⚠️ SYSTEM ALERT: You have ALREADY executed `{tool_name}` with these exact arguments. Stop."
                    logger.warning(f"[{name}] 🛑 Prevented duplicate tool: {tool_sig}")
                else:
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

                return ToolMessage(
                    content=truncate_message_content(str(content)),
                    tool_call_id=tool_id,
                    name=tool_name,
                    id=gen_uuid(),
                )

            # Gather all tool results for this step
            tool_results = await asyncio.gather(*[_process_single_tool(tc) for tc in response.tool_calls])

            for tool_msg in tool_results:
                logger.info(f"[{name}] ✅ Result ({tool_msg.name}): {str(tool_msg.content)[:100]}...")
                loop_messages.append(tool_msg)
                new_messages.append(tool_msg)

                # --- 🏅 Cognitive Evolution Path: Signal Handling ---
                
                # 1. Session Metadata Signal
                if "Session metadata set:" in str(tool_msg.content):
                    try:
                        metadata_json = str(tool_msg.content).split("Session metadata set:")[1].strip()
                        updates = json.loads(metadata_json)
                        # We update the scratchpad which correctly propagates to the graph state
                        scratchpad = state.get("scratchpad", {})
                        if "metadata" not in scratchpad:
                            scratchpad["metadata"] = {}
                        scratchpad["metadata"].update(updates)
                        logger.info(f"[{name}] 🧬 Session Metadata Updated: {updates}")
                    except Exception as e:
                        logger.warning(f"[{name}] Failed to parse session metadata signal: {e}")

                # 2. History Compression Signal
                if "[HISTORY_COMPRESSION_SIGNAL]" in str(tool_msg.content):
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

            # Phase 4 Autonomy: Checkpoint & Resume Warning
            # Give the LLM one final turn to summarize its findings before the hard cap
            if i == max_steps - 2:
                warning_msg = HumanMessage(
                    content=(
                        "⚠️ SYSTEM ALERT: You are approaching the maximum iteration limit for this exact node execution. "
                        "You have 1 step remaining. Please wrap up your current thought process, save any critical findings "
                        "using your tools (e.g. manage_memory, write_file), or prepare to yield control back to the Supervisor."
                    )
                )
                logger.warning(f"[{name}] ⚠️ Nearing max_steps ({max_steps}). Injecting wrap-up warning.")
                loop_messages.append(warning_msg)
                new_messages.append(warning_msg)

        # Loop ended (e.g., hit max_steps without returning)
        if len(new_messages) > 0 and len(response.tool_calls) > 0:
            logger.error(f"[{name}] 🔴 Hit max_steps ({max_steps}) with open tool calls. Forcing termination.")
            # Phase 4 Autonomy: Provide a clear signal that it was forcefully truncated
            truncation_msg = AIMessage(
                content="[System: Node execution reached maximum allowed steps. Execution was forcefully paused. The Supervisor should review progress and consider resuming.]"
            )
            new_messages.append(truncation_msg)

        return {
            "messages": new_messages,
            "tool_history": local_tool_history,  # For finish node knowledge harvesting
        }
