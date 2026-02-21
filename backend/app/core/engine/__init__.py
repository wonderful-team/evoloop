import json
import logging
from typing import Any

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    AIMessage,
)
from langchain_core.runnables import RunnableConfig

from app.core.engine.message_utils import (
    repair_message_history,
    smart_window_slice,
    truncate_message_content,
)
from app.core.engine.state import AgentState
from app.core.tools.executor import ToolExecutor
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.llm.factory import LLMFactory
from app.models import FileOperation
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
        final_system_prompt = AgentEngine._inject_system_context(system_prompt)

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
            system_prompt=final_system_prompt,
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
        loop_messages = [SystemMessage(content=system_prompt)] + history_messages

        if not history_messages:
            logger.warning("[AgentEngine] No history messages (only System Prompt). Skipping LLM call to prevent API errors.")
            return {"messages": []}

        logger.debug(f"--- [AgentEngine] System Prompt (First 500 chars) ---\n{system_prompt[:500]}...\n-----------------------------------------------------")

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

                    # Robustly handle JSON strings if passed by LLM instead of object
                    # Also handle potential double-encoding
                    while isinstance(context, str):
                        try:
                            context = json.loads(context)
                        except Exception:
                            logger.warning(f"[{name}] Failed to parse routing context JSON: {context[:100]}...")
                            context = {}
                            break

                    logger.info(f"[{name}] 🚀 Routing Signal: → {target} ({reason}) | Ctx: {len(context) if isinstance(context, dict) else 0} keys")

                    # Return immediately with routing information
                    return {
                        "messages": new_messages,
                        "_routing_target": target,
                        "_routing_reason": reason,
                        "_routing_context": context,  # <--- NEW
                    }

            # Execute Tools
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                logger.info(f"[{name}] 🛠️ Call: {tool_name} | Args: {json.dumps(tool_args)}")

                # Check duplication (Phase 4 Autonomy: Allow state-mutating and pollable tools)
                tool_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                from app.core.tools.registry import is_state_mutating_tool, is_pollable_tool, \
                    get_tool_affected_paths

                # We block if it's already in history AND it's neither state-mutating nor pollable
                is_blocked = (
                    tool_sig in local_tool_history
                    and not is_state_mutating_tool(tool_name)
                    and not is_pollable_tool(tool_name)
                )

                if is_blocked:
                    content = f"⚠️ SYSTEM ALERT: You have ALREADY executed `{tool_name}` with these exact arguments. Stop."
                    logger.warning(f"[{name}] 🛑 Prevented duplicate tool: {tool_sig}")
                else:
                    local_tool_history.append(tool_sig)

                    tool = tool_map.get(tool_name)
                    executor = ToolExecutor()

                    if tool:
                        try:
                            # Phase 18: Track diffs for atomic file tools
                            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
                            snapshot_paths = get_tool_affected_paths(tool_name, tool_args)

                            # Capture Snapshots
                            from app.core.memory.diff import diff_tracker
                            for path in snapshot_paths:
                                diff_tracker.capture_snapshot(path, thread_id)

                            # Execute Tool
                            content = await executor.execute(tool, tool_args, config=config)

                            # --- Diff Tracking End ---
                            for path in snapshot_paths:
                                try:
                                    operation, diff, original_content = diff_tracker.compute_diff(path, thread_id)
                                    if diff:
                                        logger.info(f"📝 Diff Detected ({operation}) on {path}:\n{diff}")
                                        # Persistence (Phase 24: Formal Changeset Tracking + Undo Support)
                                        async with session_scope() as session:
                                            # Use run_id if available for grouping, otherwise tool_id
                                            msg_id = config.get("configurable", {}).get("run_id") or tool_id
                                            file_op = FileOperation(
                                                thread_id=thread_id,
                                                message_id=str(msg_id),
                                                file_path=path,
                                                operation=operation,
                                                diff_content=diff,
                                                original_content=original_content,  # For Undo
                                            )
                                            session.add(file_op)
                                except Exception as e:
                                    logger.error(f"Failed to process diff/persistence for {path}: {e}")

                        except Exception as e:
                            content = f"Error executing {tool_name}: {e}"
                    else:
                        content = f"Error: Tool {tool_name} not found."

                # Create ToolMessage using utility for ID
                tool_msg = ToolMessage(
                    content=truncate_message_content(str(content)),
                    tool_call_id=tool_id,
                    name=tool_name,
                    id=gen_uuid(),
                )

                logger.info(f"[{name}] ✅ Result ({tool_name}): {str(content)[:200]}...")

                loop_messages.append(tool_msg)
                new_messages.append(tool_msg)

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
