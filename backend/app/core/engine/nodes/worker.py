import asyncio
import json
import logging
import os
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.context import ContextManager
from app.core.engine import AgentEngine
from app.core.engine.prompts import WorkerPromptBuilder
from app.core.engine.state import AgentState
from app.core.environment import get_awakened_state
from app.core.tools.manager import tool_manager
from app.core.tools.registry import get_tool_metadata

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

        # 1 & 2. Parallel Hydration (Optimization Phase 5)
        from app.core.engine.nodes.utils import SkillHydrator

        logger.info(f"[Worker] 🦎 Hydrating '{role_name}'...")
        
        tools_task = asyncio.to_thread(tool_manager.get_node_tools, "worker", state)
        skills_task = SkillHydrator.get_node_skills(state, "worker")

        tools, relevant_sops = await asyncio.gather(tools_task, skills_task)
        
        # 2a. Fallback Recovery Skill Injection
        # During macro fallback, we explicitly inject the failed skill's instructions 
        # as the highest priority SOP for the Worker to reference.
        metadata = config.get("metadata", {})
        original_skill_id = metadata.get("original_skill_id")
        if original_skill_id:
            try:
                from app.infrastructure.database.sql.database import session_scope
                from app.models.learning import LearnedSkill
                from sqlalchemy import select
                async with session_scope() as session:
                    # Fetch specific skill
                    stmt = select(LearnedSkill).where(LearnedSkill.id == original_skill_id)
                    result = await session.execute(stmt)
                    skill = result.scalar_one_or_none()
                    if skill and skill.instructions:
                        # Append to Sops map, avoiding duplicates if already retrieved semantically
                        if not any(hasattr(s, 'id') and getattr(s, 'id') == original_skill_id for s in relevant_sops):
                            relevant_sops.insert(0, skill)
                            logger.info(f"[Worker] 📜 Force-injected Expert Guide for Skill ID {skill.id} (Fallback Recovery)")
                            
                    # Fetch Generic Macro Healer (Fallback Baseline)
                    healer_stmt = select(LearnedSkill).where(LearnedSkill.name == "Macro Recovery Specialist")
                    healer_result = await session.execute(healer_stmt)
                    generic_healer = healer_result.scalar_one_or_none()
                    if generic_healer:
                        if not any(getattr(s, 'id', None) == generic_healer.id for s in relevant_sops):
                            relevant_sops.append(generic_healer)
                            logger.info("[Worker] 📜 Force-attached Generic Macro Healer SOP (Fallback Baseline)")
            except Exception as e:
                logger.error(f"[Worker] Failed to fetch fallback skill instructions: {e}")

        # 2b. Generic Context Enrichment from Awakening System
        ctx = ContextManager.current()
        awakened_env = get_awakened_state()
        has_android = ctx.metadata.get("has_android", False)

        if awakened_env and awakened_env.relevant_concepts:
            if isinstance(ctx.spatial_awareness, dict):
                insights = ctx.spatial_awareness.setdefault("insights", [])
                for concept in awakened_env.relevant_concepts:
                    insights.append(f"💡 {concept.name}: {concept.description}")
            else:
                for concept in awakened_env.relevant_concepts:
                    ctx.spatial_awareness.append(f"💡 {concept.name}: {concept.description}")
            logger.info(f"[Worker] 🧠 Enriched context with {len(awakened_env.relevant_concepts)} relevant concepts from Brain.")

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
                max_steps=settings.WORKER_AGENT_MAX_STEPS,
            )

            # 5. Post-Processing (Absorbed from Operator)
            return self._post_process_result(state, engine_result, execution_ticket, role_name)

        except Exception as e:
            logger.error(f"[Worker] 💥 '{role_name}' failed: {e}")
            return {
                "messages": [AIMessage(content=f"Worker '{role_name}' failed: {e}")],
                "next_node": "supervisor"
            }

        return return_state

    def _post_process_result(
        self,
        state: AgentState,
        engine_result: dict,
        execution_ticket: dict,
        role_name: str
    ) -> dict[str, Any]:
        """
        Universal post-processing pipeline (absorbed from OperatorNode).
        Handles: result summary, cache invalidation, verification capture, MCP interception,
        and subtask result collection (Phase 1).
        """
        last_msg = engine_result["messages"][-1]
        content = last_msg.content if isinstance(last_msg, AIMessage) else ""
        tool_history = engine_result.get("tool_history", [])
        routing_target = engine_result.get("_routing_target")

        logger.info(f"[Worker][{role_name}] Loop finished. Content len: {len(content)}, Tools used: {len(tool_history)}, Target: {routing_target}")

        summary = f"**{role_name} Report**:\n{content}\n\n(Tools used: {len(tool_history)})"

        return_state: dict[str, Any] = {
            "messages": [AIMessage(content=summary)],
            "next_node": routing_target or "supervisor",
        }

        # --- 🏅 Phase 1: Subtask Result Collection ---
        # If this is a subtask execution, store result for aggregation
        agent_config = execution_ticket.get("agent_config", {})
        if agent_config.get("is_subtask"):
            subtask_id = execution_ticket.get("subtask_id", "unknown")
            parent_task_id = execution_ticket.get("parent_task_id", "unknown")

            subtask_result = {
                "subtask_id": subtask_id,
                "status": "completed",
                "result": content,
                "tools_used": tool_history,
                "timestamp": asyncio.get_event_loop().time(),
            }

            # Store in scratchpad for aggregation
            scratchpad = state.get("scratchpad", {})
            if "subtask_results" not in scratchpad:
                scratchpad["subtask_results"] = []
            scratchpad["subtask_results"].append(subtask_result)

            # Check if all subtasks are complete
            pending_agg = scratchpad.get("_pending_aggregation", {})
            if pending_agg:
                expected_count = pending_agg.get("expected_count", 0)
                current_count = len(scratchpad["subtask_results"])

                logger.info(f"[Worker] Subtask {subtask_id} completed ({current_count}/{expected_count})")

                # Note: Aggregation is handled by Supervisor checking scratchpad
                # Worker always returns to Supervisor for centralized control

            return_state["scratchpad"] = scratchpad

        # 5a. Cache Invalidation (Universal via Metadata)
        # Instead of a hardcoded list, we use the tool registry's metadata.
        has_changes = False
        for t_sig in tool_history:
            tool_name = t_sig.split(":")[0] if ":" in t_sig else t_sig
            meta = get_tool_metadata(tool_name)
            if meta and meta.get("is_state_mutating"):
                has_changes = True
                logger.info(f"[Worker][{role_name}] ♻️ State mutation detected via tool '{tool_name}' - Invalidating caches")
                break

        if has_changes:
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
