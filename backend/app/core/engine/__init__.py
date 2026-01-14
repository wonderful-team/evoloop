import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.engine.message_utils import repair_message_history, smart_window_slice
from app.core.engine.state import AgentState
from app.core.llm.factory import LLMFactory
from app.core.tools.executor import ToolExecutor
from app.domain.system.service import SystemConfigService
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
        name: str = "Agent"
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
            from app.core.memory.pruner import ContextPruner
            raw_messages = ContextPruner.prune_messages(raw_messages)
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
            name=name
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
        name: str
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
            logger.info(f"--- {name} Loop Step {i+1} ---")

            # Invoke LLM
            response = await llm_with_tools.ainvoke(loop_messages, config=config)

            # OBSERVE: LLM Response (Thinking)
            if response.content:
                logger.info(f"[{name}] 🧠 Thinking: {response.content[:300]}..." if len(response.content) > 300 else f"[{name}] 🧠 Thinking: {response.content}")

            loop_messages.append(response)
            new_messages.append(response)

            if not response.tool_calls:
                logger.info(f"[{name}] 🏁 Finished with text response.")
                break

            # Execute Tools
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                logger.info(f"[{name}] 🛠️ Call: {tool_name} | Args: {json.dumps(tool_args)}")

                # Check duplication
                tool_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                if tool_sig in local_tool_history and tool_name != "manage_file":
                    content = f"⚠️ SYSTEM ALERT: You have ALREADY executed `{tool_name}` with these exact arguments. Stop."
                    logger.warning(f"[{name}] 🛑 Prevented duplicate tool: {tool_sig}")
                else:
                    local_tool_history.append(tool_sig)

                    tool = tool_map.get(tool_name)
                    executor = ToolExecutor()

                    if tool:
                        try:
                            # --- Diff Tracking Start ---
                            snapshot_path = None
                            from app.core.memory.diff import diff_tracker

                            if tool_name == "manage_file" and isinstance(tool_args, dict):
                                arg_path = tool_args.get("absolute_path")
                                action = tool_args.get("action")
                                if arg_path and action in ["create", "update_block", "write"]:
                                     snapshot_path = arg_path
                                     diff_tracker.capture_snapshot(snapshot_path)

                            # Execute Tool
                            content = await executor.execute(tool, tool_args, config=config)

                            # --- Diff Tracking End ---
                            if snapshot_path:
                                diff = diff_tracker.compute_diff(snapshot_path)
                                if diff:
                                    logger.info(f"📝 Diff Detected:\n{diff}")
                                    content = str(content) + f"\n\n[Version Control] Changes Applied:\n```diff\n{diff}\n```"
                                else:
                                    # If no diff but success, maybe it was a create or identical replace
                                    pass

                        except Exception as e:
                            content = f"Error executing {tool_name}: {e}"
                    else:
                        content = f"Error: Tool {tool_name} not found."

                # Create ToolMessage using utility for ID
                tool_msg = ToolMessage(content=str(content), tool_call_id=tool_id, name=tool_name, id=gen_uuid())

                logger.info(f"[{name}] ✅ Result ({tool_name}): {str(content)[:200]}...")

                loop_messages.append(tool_msg)
                new_messages.append(tool_msg)

        return {
            "messages": new_messages
        }
