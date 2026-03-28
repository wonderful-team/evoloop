import asyncio
import copy
import json
import logging
import os
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from app.core.config import settings
from app.core.context import ContextManager
from app.core.engine import AgentEngine
from app.core.engine.message_utils import get_message_text
from app.core.engine.prompts import WorkerPromptBuilder
from app.core.engine.state import AgentState
from app.core.environment import get_awakened_state
from app.core.tools.manager import tool_manager
from app.core.tools.registry import get_tool_metadata
from app.constants import DEFAULT_PROJECT_ID, RoutingTarget

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
        # Implementation of WorkerNode...
        # Unified Hydration (Phase 1 Optimization)
        from app.core.engine.middleware import EvoContextMiddleware
        state = await EvoContextMiddleware.hydrate(state, config)
        
        execution_ticket = state.get("execution_ticket")

        if not execution_ticket or not execution_ticket.get("agent_config"):
            # Create a default agent_config for backward compatibility
            # This handles cases where router maps directly to worker without full ticket
            logger.warning("[Worker] No AgentConfig found in ticket! Using default configuration.")
            blackboard = state.get("blackboard") or {}
            route_reason = blackboard.get("route_reason", "Execute task")
            execution_ticket = {
                "ticket_type": "task",
                "topic": route_reason,
                "agent_config": {
                    "role_name": "Worker",
                    "system_instructions": "Execute the following task steps accurately and provide the result.",
                }
            }

        agent_config = execution_ticket["agent_config"]
        role_name = agent_config.get("role_name", "Specialist")

        # 1 & 2. Parallel Hydration (Optimization Phase 5)
        logger.info(f"[Worker] 🦎 Hydrating '{role_name}'...")

        from app.core.engine.nodes.utils import SkillHydrator
        
        # 检查是否有多技能工作流
        skill_ids = execution_ticket.get("skill_ids") or []
        workflow_mode = execution_ticket.get("workflow_mode", "single")
        
        # 向后兼容：如果只有单个 skill_id，转换为列表
        if not skill_ids and execution_ticket.get("skill_id"):
            skill_ids = [execution_ticket["skill_id"]]
            workflow_mode = "single"
        
        # 判断是否为多步骤工作流
        is_multi_skill_workflow = workflow_mode == "sequential" and len(skill_ids) > 1
        
        if is_multi_skill_workflow:
            # 多技能工作流：直接加载指定技能
            logger.info(f"[Worker] 🔄 Multi-skill workflow detected: {skill_ids}")
            tools_task = asyncio.to_thread(tool_manager.get_node_tools, "worker", state)
            
            # 按顺序加载所有技能
            skills_task = self._load_skills_by_ids(skill_ids)
            tools, relevant_sops = await asyncio.gather(tools_task, skills_task)
        else:
            # 单技能或传统模式
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

        # 2b. Context already enriched via EvoContextMiddleware
        ctx = ContextManager.current()
        # Phase 4: Inject is_subtask for downstream prompt fragments (Awakening)
        if agent_config.get("is_subtask"):
            ctx.metadata["is_subtask"] = True

        logger.info(f"[Worker] 🧠 Utilizing enriched context for role '{role_name}'")
        
        # 3. Construct Prompts (Using Builder & Phase 1 Blackboard)
        blackboard = state.get("blackboard") or {}

        # Use full plan for complete context
        # Previously simplified plan caused loss of step descriptions and dependencies
        full_plan = state.get("structured_plan") or state.get("current_plan") or blackboard.get("plan")

        # 3b. Focus-File Data Retrieval (data only, rendering handled by template)
        focus_files = await self._hydrate_focus_files(execution_ticket, ctx)

        prompt_builder = WorkerPromptBuilder(
            agent_config,
            blackboard,
            skills=relevant_sops,
            ticket=execution_ticket,
            focus_files=focus_files,
            plan=full_plan
        )
        system_prompt = prompt_builder.build(config)

        mission_msg = prompt_builder.build_mission_message()
        messages = [HumanMessage(content=mission_msg)]

        # 4. Execute (Using AgentEngine)
        try:
            # 判断是否为多技能工作流
            skill_ids = execution_ticket.get("skill_ids") or []
            workflow_mode = execution_ticket.get("workflow_mode", "single")
            is_multi_skill_workflow = workflow_mode == "sequential" and len(skill_ids) > 1

            if is_multi_skill_workflow:
                # 多技能顺序执行
                logger.info(f"[Worker] 🚀 Launching sequential workflow with {len(skill_ids)} skills...")
                return await self._execute_sequential_workflow(
                    state=state,
                    config=config,
                    skills=relevant_sops,
                    tools=tools,
                    execution_ticket=execution_ticket,
                    agent_config=agent_config,
                    role_name=role_name
                )

            # 单技能传统执行
            logger.info(f"[Worker] 🚀 Launching '{role_name}' atomic loop...")

            # Subtasks should NOT inherit full message history to prevent "Echo Chamber" loops.
            # Use deepcopy for subtasks to prevent state pollution between parallel executions.
            if agent_config.get("is_subtask"):
                worker_state = copy.deepcopy(state)
            else:
                worker_state = state.copy()
            worker_state["messages"] = messages

            engine_result = await AgentEngine.run_node(
                state=worker_state,
                config=config,
                system_prompt=system_prompt,
                tools=tools,
                name=f"Worker-{role_name}",
                max_steps=1 if agent_config.get("is_subtask") else settings.WORKER_AGENT_MAX_STEPS,
                is_subtask=agent_config.get("is_subtask", False),
            )

            # 5. Unified Dispatching (Phase 2)
            signal = engine_result.get("signal")
            if signal:
                from app.core.engine.dispatcher import SignalDispatcher
                return await SignalDispatcher.dispatch(state, signal, config)

            # Standard post-processing (Absorbed logic)
            return self._post_process_result(state, engine_result, execution_ticket, role_name)

        except Exception as e:
            logger.error(f"[Worker] 💥 '{role_name}' failed: {e}")
            return {
                "messages": [AIMessage(content=f"Worker '{role_name}' failed: {e}")],
                "next_node": RoutingTarget.SUPERVISOR
            }

    async def _load_skills_by_ids(self, skill_ids: list[int]) -> list[Any]:
        """按 ID 列表加载技能（用于多技能工作流）"""
        from app.core.engine.nodes.utils import SkillHydrator
        
        skills = []
        for sid in skill_ids:
            skill = await SkillHydrator.get_skill_by_id(sid)
            if skill:
                skills.append(skill)
            else:
                logger.warning(f"[Worker] Skill ID {sid} not found or inactive")
        return skills

    async def _execute_sequential_workflow(
        self,
        state: AgentState,
        config: RunnableConfig,
        skills: list[Any],
        tools: list,
        execution_ticket: dict,
        agent_config: dict,
        role_name: str
    ) -> dict[str, Any]:
        """
        顺序执行多个技能，上一步输出作为下一步输入
        """
        from app.core.engine.prompts import WorkerPromptBuilder
        from app.core.context import ContextManager
        
        results = []
        blackboard = state.get("blackboard") or {}
        ctx = ContextManager.current()
        full_plan = state.get("structured_plan") or state.get("current_plan") or blackboard.get("plan")
        
        for i, skill in enumerate(skills):
            is_last = (i == len(skills) - 1)
            is_first = (i == 0)
            
            logger.info(f"[Worker] 🔄 Workflow Step {i+1}/{len(skills)}: {skill.name}")
            
            # 构建工作流上下文
            workflow_context = {
                "step_number": i + 1,
                "total_steps": len(skills),
                "is_first_step": is_first,
                "is_last_step": is_last,
                "previous_results": results,
                "current_skill": {
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description or ""
                }
            }
            
            # 更新 ticket 用于当前步骤
            step_ticket = copy.deepcopy(execution_ticket)
            step_ticket["workflow_context"] = workflow_context
            step_ticket["skill_id"] = skill.id  # 当前步骤的技能 ID
            step_ticket["topic"] = f"Step {i+1}: {skill.name}"
            
            # 加载 Focus Files（只加载一次）
            focus_files = await self._hydrate_focus_files(execution_ticket, ctx) if is_first else []
            
            # 构建 Prompt
            prompt_builder = WorkerPromptBuilder(
                agent_config,
                blackboard,
                skills=[skill],  # 只传递当前技能
                ticket=step_ticket,
                focus_files=focus_files,
                plan=full_plan
            )
            system_prompt = prompt_builder.build(config)
            mission_msg = prompt_builder.build_mission_message()
            
            # 构建消息
            if is_first:
                messages = [HumanMessage(content=mission_msg)]
            else:
                # 传递上一步的输出作为上下文
                prev_output = results[-1].get("output", "") if results else ""
                enhanced_mission = f"{mission_msg}\n\n[Previous Step Output]: {prev_output[:500]}"
                messages = [HumanMessage(content=enhanced_mission)]
            
            try:
                # 执行当前步骤
                worker_state = copy.deepcopy(state) if agent_config.get("is_subtask") else state.copy()
                worker_state["messages"] = messages
                
                engine_result = await AgentEngine.run_node(
                    state=worker_state,
                    config=config,
                    system_prompt=system_prompt,
                    tools=tools,
                    name=f"Worker-{role_name}-Step{i+1}",
                    max_steps=1 if agent_config.get("is_subtask") else settings.WORKER_AGENT_MAX_STEPS,
                    is_subtask=agent_config.get("is_subtask", False),
                )
                
                # 提取步骤输出
                last_msg = engine_result["messages"][-1]
                step_output = get_message_text(last_msg) if isinstance(last_msg, AIMessage) else ""
                
                results.append({
                    "skill_id": skill.id,
                    "skill_name": skill.name,
                    "output": step_output,
                    "status": "success"
                })
                
                # 检查是否需要中断
                if "[ERROR:" in step_output or step_output.strip().startswith("Error:"):
                    logger.error(f"[Worker] Workflow failed at step {i+1}")
                    summary = f"Workflow failed at step {i+1}/{len(skills)}: {skill.name}\n\n{step_output}"
                    return {
                        "messages": [AIMessage(content=summary)],
                        "next_node": RoutingTarget.SUPERVISOR,
                        "workflow_results": results
                    }
                    
            except Exception as e:
                logger.error(f"[Worker] Step {i+1} failed: {e}")
                results.append({
                    "skill_id": skill.id,
                    "skill_name": skill.name,
                    "output": str(e),
                    "status": "failed"
                })
                return {
                    "messages": [AIMessage(content=f"Workflow failed at step {i+1}: {e}")],
                    "next_node": RoutingTarget.SUPERVISOR,
                    "workflow_results": results
                }
        
        # 所有步骤完成
        final_result = results[-1] if results else {"output": "No output"}
        summary_lines = [
            f"✅ Workflow completed ({len(skills)} steps)",
            "",
            "Execution Summary:"
        ]
        for i, r in enumerate(results):
            status_icon = "✅" if r["status"] == "success" else "❌"
            output_preview = r["output"][:100] + "..." if len(r["output"]) > 100 else r["output"]
            summary_lines.append(f"  {status_icon} Step {i+1} [{r['skill_name']}]: {output_preview}")
        
        summary_lines.append("")
        summary_lines.append(f"Final Output:\n{final_result.get('output', '')}")
        
        return {
            "messages": [AIMessage(content="\n".join(summary_lines))],
            "next_node": RoutingTarget.FINISH,
            "workflow_results": results
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
        Handles: result summary, cache invalidation, verification capture, MCP interception,
        and subtask result collection (Phase 1).
        """
        last_msg = engine_result["messages"][-1]
        content = get_message_text(last_msg) if isinstance(last_msg, AIMessage) else ""
        tool_history = engine_result.get("tool_history", [])
        routing_target = engine_result.get("_routing_target")

        logger.info(f"[Worker][{role_name}] Loop finished. Content len: {len(content)}, Tools used: {len(tool_history)}, Target: {routing_target}")

        # Determine structured outcome (replaces text-based [STATUS:] tag injection)
        if "[ERROR:" in content or content.strip().startswith("Error:"):
            worker_outcome = "failed"
        else:
            worker_outcome = "success"

        from app.utils import render_template
        summary = render_template(
            "report/response.prompt.j2",
            success=(worker_outcome == "success"),
            message=f"{role_name} Report",
            details=content,
            note=f"Tools used: {len(tool_history)}"
        )

        return_state: dict[str, Any] = {
            "messages": [AIMessage(content=summary)],
            "next_node": routing_target or RoutingTarget.FINISH,
        }

        # --- Structured outcome via Blackboard ---
        blackboard = state.get("blackboard") or {}
        agent_config = execution_ticket.get("agent_config", {})
        # Subtask workers do NOT set worker_outcome directly;
        # the Aggregator determines the final outcome after merging all parallel results.
        if not agent_config.get("is_subtask"):
            blackboard["worker_outcome"] = worker_outcome

        # --- Subtask Result Collection ---
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

            if "subtask_results" not in blackboard or blackboard["subtask_results"] is None:
                blackboard["subtask_results"] = []
            
            blackboard["subtask_results"].append(subtask_result)
            
            pending_agg = blackboard.get("pending_aggregation", {})
            if pending_agg:
                expected_count = pending_agg.get("expected_count", 0)
                current_count = len(blackboard["subtask_results"])
                logger.debug(f"[Worker] 📊 Subtask completion progress: {current_count}/{expected_count}")

        return_state["blackboard"] = blackboard

        # 5a. Cache Invalidation (Universal via Metadata)
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

    async def _hydrate_focus_files(self, ticket: dict, ctx) -> list[dict]:
        """
        Retrieve focus-file data as structured objects.
        Returns a list of dicts with keys: rel_path, status, content/detail.
        Rendering is handled by the Jinja2 template.
        """
        focus_paths = ticket.get("focus_paths", [])
        if not focus_paths:
            return []

        cwd = ctx.working_directory or ""
        results = []

        for path_item in focus_paths:
            try:
                # 1. Path Normalization & Integration (Handle absolute host paths from Supervisor)
                if os.path.isabs(path_item):
                    full_path = path_item
                    # Try to derive a meaningful relative path for the Agent's view
                    from app.core.engine.prompts.utils import get_mapped_cwd
                    display_path = get_mapped_cwd(path_item)
                else:
                    full_path = os.path.join(cwd, path_item) if cwd else path_item
                    display_path = path_item

                if not os.path.exists(full_path):
                    results.append({"rel_path": display_path, "status": "missing"})
                    continue

                if os.path.isdir(full_path):
                    # For directories, provide a basic info instead of failing
                    results.append({
                        "rel_path": display_path, 
                        "status": "directory", 
                        "detail": "This is a directory. Use 'list_directory(tree=True)' to examine."
                    })
                    continue

                size = os.path.getsize(full_path)
                if size > 30_000:
                    results.append({"rel_path": display_path, "status": "skipped", "detail": f"Too large: {size}b"})
                    continue

                with open(full_path, encoding="utf-8") as f:
                    file_content = f.read()
                results.append({"rel_path": display_path, "status": "ok", "content": file_content})
            except Exception as e:
                results.append({"rel_path": path_item, "status": "error", "detail": str(e)})

        return results


# Singleton
worker_node = WorkerNode()
