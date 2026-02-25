import asyncio
import json
import logging
import os
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.engine import AgentEngine
from app.core.engine.prompts import WorkerPromptBuilder
from app.core.engine.state import AgentState
from app.core.environment import get_awakened_state
from app.core.tools.manager import tool_manager

logger = logging.getLogger(__name__)


class WorkerNode:
    """
    The Universal Worker Node (v5.0).
    
    A neutral, ephemeral executor that acquires expertise dynamically at runtime
    through Skill SOPs and tool injection via the ExecutionTicket.
    
    Absorbs infrastructure from legacy Operator, Researcher, Documenter, and Finish nodes:
    - Post-processing hooks (cache invalidation, verification capture, MCP interception)
    - Focus-file injection (Attention Guidance from Supervisor handoff)
    - Generic context enrichment from Awakening System
    """

    async def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        execution_ticket = state.get("execution_ticket")

        if not execution_ticket or not execution_ticket.get("agent_config"):
            logger.error("[Worker] No AgentConfig found in ticket! Aborting.")
            return {
                "messages": [AIMessage(content="Error: I was summoned but given no instructions (missing AgentConfig).")],
                "next_node": "supervisor"
            }

        agent_config = execution_ticket["agent_config"]
        role_name = agent_config.get("role_name", "Specialist")
        instructions = agent_config.get("system_instructions", "You are a helpful assistant.")
        tool_names = agent_config.get("tools", [])

        # 1 & 2. Parallel Hydration (Optimization Phase 5)
        from app.core.engine.nodes.utils import SkillHydrator

        logger.info(f"[Worker] 🦎 Hydrating '{role_name}'...")
        
        tools_task = asyncio.to_thread(tool_manager.get_node_tools, "worker", state)
        skills_task = SkillHydrator.get_node_skills(state, "worker")

        tools, relevant_sops = await asyncio.gather(tools_task, skills_task)

        # 2b. Generic Context Enrichment from Awakening System
        from app.core.context import ContextManager
        ctx = ContextManager.current()
        awakened_env = get_awakened_state()
        if awakened_env and awakened_env.relevant_concepts:
            for concept in awakened_env.relevant_concepts:
                ctx.spatial_awareness.append(f"💡 {concept.name}: {concept.description}")
            logger.info(f"[Worker] 🧠 Enriched context with {len(awakened_env.relevant_concepts)} concepts from Brain.")

        # 3. Construct Prompts (Using Builder)
        scratchpad = state.get("scratchpad", {})
        clipboard = scratchpad.get("workspace_clipboard", [])

        prompt_builder = WorkerPromptBuilder(
            agent_config,
            execution_ticket,
            skills=relevant_sops,
            clipboard=clipboard
        )
        system_prompt = prompt_builder.build(config)

        # 3b. Focus-File Injection (Absorbed from Operator)
        focus_prompt = await self._hydrate_focus_files(execution_ticket, ctx)
        if focus_prompt:
            system_prompt += f"\n\n{focus_prompt}"

        mission_msg = prompt_builder.build_mission_message()
        messages = [HumanMessage(content=mission_msg)]

        # 4. Execute (Using AgentEngine)
        try:
            logger.info(f"[Worker] 🚀 Launching '{role_name}' atomic loop...")

            engine_result = await AgentEngine.run_node(
                state={**state, "messages": messages},
                config=config,
                system_prompt=system_prompt,
                tools=tools,
                name=f"Worker-{role_name}",
                max_steps=settings.DYNAMIC_AGENT_MAX_STEPS,
            )

            # 5. Post-Processing (Absorbed from Operator)
            return self._post_process_result(state, engine_result, execution_ticket, role_name)

        except Exception as e:
            logger.error(f"[Worker] 💥 '{role_name}' failed: {e}")
            return {
                "messages": [AIMessage(content=f"Worker '{role_name}' failed: {e}")],
                "next_node": "supervisor"
            }

    def _post_process_result(
        self,
        state: AgentState,
        engine_result: dict,
        execution_ticket: dict,
        role_name: str
    ) -> dict[str, Any]:
        """
        Universal post-processing pipeline (absorbed from OperatorNode).
        Handles: result summary, cache invalidation, verification capture, MCP interception.
        """
        last_msg = engine_result["messages"][-1]
        content = last_msg.content if isinstance(last_msg, AIMessage) else ""

        tool_history = engine_result.get("tool_history", [])
        logger.info(f"[Worker][{role_name}] Loop finished. Content len: {len(content)}, Tools used: {len(tool_history)}")

        summary = f"**{role_name} Report**:\n{content}\n\n(Tools used: {len(tool_history)})"

        return_state: dict[str, Any] = {
            "messages": [AIMessage(content=summary)],
            "next_node": "supervisor",
        }

        # 5a. Cache Invalidation (from Operator)
        write_tools = {"write_file", "edit_file", "manage_file", "write_document", "edit_document"}
        has_changes = any(
            any(wt in t_sig for wt in write_tools)
            for t_sig in tool_history
        )
        if has_changes:
            logger.info(f"[Worker][{role_name}] ♻️ File changes detected - Invalidating caches")
            return_state["workspace_context"] = {"structure": None, "structure_updated_at": 0.0}

        # 5b. Verification Signal Capture (from Operator)
        verification_summary = {"status": "unverified", "signals": []}
        for t_sig in tool_history:
            tool_name = t_sig.split(":")[0] if ":" in t_sig else t_sig
            if tool_name not in verification_summary["signals"]:
                verification_summary["signals"].append(tool_name)

            # 5c. MCP Server Interception (from Operator + legacy Specialist)
            if tool_name == "use_mcp_server":
                try:
                    args_json = t_sig.split(":", 1)[1]
                    args = json.loads(args_json)
                    server_name = args.get("server_name")
                    if server_name:
                        req_servers = set(execution_ticket.get("mcp_servers_required", []))
                        req_servers.add(server_name)
                        execution_ticket["mcp_servers_required"] = list(req_servers)
                        return_state["execution_ticket"] = execution_ticket
                        logger.info(f"[Worker] 🔌 Appended MCP server '{server_name}' to execution_ticket.")
                except Exception as e:
                    logger.error(f"[Worker] Failed to parse use_mcp_server arguments: {e}")

        return_state["verification_status"] = verification_summary
        return return_state

    async def _hydrate_focus_files(self, ticket: dict, ctx) -> str:
        """
        Inject focus-file contents into the prompt (absorbed from OperatorNode._hydrate_context).
        Reads files specified in ExecutionTicket.focus_paths.
        """
        focus_paths = ticket.get("focus_paths", [])
        if not focus_paths:
            return ""

        cwd = ctx.working_directory or ""
        output = [
            "### ATTENTION GUIDANCE (Focus Files)",
            f"The Supervisor has identified {len(focus_paths)} focus files for this mission:"
        ]

        for rel_path in focus_paths:
            try:
                full_path = os.path.join(cwd, rel_path) if cwd else rel_path
                if not os.path.exists(full_path):
                    output.append(f"- [MISSING] {rel_path}")
                    continue

                size = os.path.getsize(full_path)
                if size > 30_000:
                    output.append(f"- [SKIPPED] {rel_path} (Too large: {size}b)")
                    continue

                with open(full_path, encoding="utf-8") as f:
                    file_content = f.read()
                output.append(f"\n--- FILE: {rel_path} ---\n{file_content}\n--- END OF FILE ---\n")
            except Exception as e:
                output.append(f"- [ERROR] {rel_path}: {e}")

        return "\n".join(output) + "\n"


# Singleton
worker_node = WorkerNode()
