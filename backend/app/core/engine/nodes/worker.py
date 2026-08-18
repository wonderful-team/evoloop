import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.context import ContextManager
from app.core.engine.nodes.base import BaseAgentNode
from app.core.engine.nodes.prompts import WorkerPromptBuilder
from app.core.engine.nodes.utils.skill_resolver import SkillResolver
from app.core.engine.nodes.utils.worker_result_processor import process_worker_result
from app.core.engine.routers import RoutingTarget
from app.core.engine.schemas import EngineResult
from app.core.engine.skill_hydrator import SkillHydrator
from app.core.engine.state import AgentState, StateUpdate
from app.core.tools.manager import tool_manager

logger = logging.getLogger(__name__)


class WorkerNode(BaseAgentNode):
    """
    The Universal Worker Node.
    """

    def __init__(self):
        super().__init__(node_name="Worker", max_steps=settings.WORKER_AGENT_MAX_STEPS)

    async def prepare_state(self, state: AgentState, config: dict) -> StateUpdate | None:
        execution_ticket = state.ticket
        if not execution_ticket:
            raise ValueError("[WorkerNode] ExecutionTicket is missing.")

        if not execution_ticket.agent_config:
            raise ValueError("[WorkerNode] ExecutionTicket.agent_config is missing.")

        if not state.structured_plan and not state.current_plan:
            thread_id = config.get("configurable", {}).get("thread_id")
            if thread_id:
                try:
                    from app.infrastructure.database.resource_manager import (
                        db_resource_manager,
                    )
                    from app.models.planning import Plan as DBPlan

                    def _sync_load_plan(tid: str):
                        engine = db_resource_manager.sync_engine
                        if not engine:
                            return None
                        with Session(engine) as session:
                            stmt = select(DBPlan).where(DBPlan.thread_id == tid)
                            plan = session.execute(stmt).scalar_one_or_none()
                            if plan and plan.steps:
                                return {
                                    "id": plan.id,
                                    "title": plan.title,
                                    "status": plan.status,
                                    "steps": [
                                        {
                                            "id": s.id,
                                            "title": s.title,
                                            "status": s.status,
                                            "order": s.order,
                                        }
                                        for s in plan.steps
                                    ],
                                }
                            return None

                    plan_dict = await asyncio.to_thread(_sync_load_plan, thread_id)
                    if plan_dict:
                        state.structured_plan = plan_dict
                        logger.info(
                            f"[Worker] Loaded plan from DB: {plan_dict['title']} ({len(plan_dict['steps'])} steps)"
                        )
                except (ImportError, SQLAlchemyError) as e:
                    logger.warning(f"[Worker] Failed to load plan from DB: {e}", exc_info=True)

        return None

    async def build_prompt_pair(self, state: AgentState, config: dict) -> tuple[str, str]:
        execution_ticket = state.ticket
        agent_config = execution_ticket.agent_config if execution_ticket else None
        blackboard = state
        ctx = ContextManager.current()

        full_plan = state.structured_plan or state.current_plan
        focus_paths = execution_ticket.focus_paths if execution_ticket else []
        relevant_sops = state.relevant_sops

        prompt_builder = WorkerPromptBuilder(
            agent_config,
            blackboard,
            skills=relevant_sops,
            ticket=execution_ticket,
            focus_paths=focus_paths,
            plan=full_plan,
        )

        static_system_prompt = await prompt_builder.build(config)

        from app.core.engine.nodes.utils.node_utils import get_mapped_cwd
        actual_cwd = get_mapped_cwd(ctx.working_directory or ctx.metadata.get("cwd", ""))

        from app.core.environment import get_telemetry_dict

        telemetry = get_telemetry_dict()

        mission_msg = prompt_builder.build_mission_message(
            environment_block=ctx.environment_block or "",
            cwd=actual_cwd,
            telemetry=telemetry,
            plan=full_plan,
            session_goal=state.session_goal,
        )

        return static_system_prompt, mission_msg

    async def get_tools(self, state: AgentState) -> list[Any]:
        tools = await tool_manager.get_node_tools("worker", state)
        tool_names = [t.name for t in tools]
        logger.info(f"[Worker] Loaded {len(tools)} tools: {tool_names}")
        return tools

    @staticmethod
    def _build_worker_view(messages: list, is_resuming: bool = False) -> list:
        result: list = []
        tail_messages = []
        if is_resuming:
            tail_messages = messages[-10:] if len(messages) >= 10 else messages

        for msg in messages:
            role = msg.role
            if role == "system":
                result.append(msg)
            elif role == "user" and not msg.name:
                result.append(msg)
            elif is_resuming and msg in tail_messages:
                if msg not in result:
                    result.append(msg)
        return result

    async def _build_fallback_outcome(
        self,
        original_state: AgentState,
        engine_result: EngineResult,
        config: dict
    ) -> StateUpdate:
        execution_ticket = original_state.ticket
        role_name = (
            execution_ticket.agent_config.role_name
            if execution_ticket and execution_ticket.agent_config else "Worker"
        )
        result = await process_worker_result(
            self.node_name,
            original_state,
            engine_result,
            execution_ticket,
            role_name,
            config,
        )
        return result

    async def __call__(self, state: AgentState, config: dict) -> StateUpdate:
        from app.core.engine.state import ensure_state

        state = ensure_state(state)

        execution_ticket = state.ticket
        if execution_ticket:
            logger.info(
                f"[Worker] ExecutionTicket received | "
                f"topic='{execution_ticket.topic}' | "
                f"skills={execution_ticket.skill_ids} | "
                f"acceptance={execution_ticket.acceptance_criteria} | "
                f"role={(execution_ticket.agent_config.role_name if execution_ticket.agent_config else 'Worker')}"
            )

        skill_ids = execution_ticket.skill_ids or [] if execution_ticket else []
        workflow_mode = execution_ticket.workflow_mode or "single" if execution_ticket else "single"
        is_multi_skill_workflow = workflow_mode == "sequential" and len(skill_ids) > 1

        if skill_ids:
            relevant_sops = await SkillResolver.load_skills_by_ids(skill_ids)
        else:
            relevant_sops = await SkillHydrator.get_node_skills(state, "worker")

        relevant_sops = await SkillResolver.inject_fallback_sops(relevant_sops, config)
        state.relevant_sops = relevant_sops

        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
        role_name = (
            execution_ticket.agent_config.role_name
            if execution_ticket and execution_ticket.agent_config else "Worker"
        )
        task_label = role_name
        if execution_ticket and execution_ticket.topic:
            task_label = f"{role_name}: {execution_ticket.topic}"

        from app.core.monitoring.activity import activity_monitor

        await activity_monitor.update_agent_state(
            thread_id=thread_id,
            mode="EXECUTING",
            task_name=task_label,
            task_status="Initializing...",
            active_skills=[
                {
                    "id": sop.id,
                    "name": sop.name,
                    "description": sop.description,
                }
                for sop in relevant_sops
                if hasattr(sop, "id")
            ] or None
        )

        if is_multi_skill_workflow:
            logger.info("[Worker] 🔄 Delegating to sequential workflow...")
            from app.core.engine.message.native_classes import AIMessage

            return StateUpdate(
                messages=[
                    AIMessage(content=f"Starting sequential workflow with {len(skill_ids)} skills.")
                ],
                next_node=RoutingTarget.SEQUENTIAL_WORKFLOW,
                workflow_plan=relevant_sops,
                workflow_step_index=0,
                workflow_results=[],
            )

        is_resuming = execution_ticket.is_resuming if execution_ticket else False
        filtered_messages = self._build_worker_view(state.messages, is_resuming=is_resuming)
        if len(filtered_messages) < len(state.messages):
            logger.info(
                f"[Worker] Message view built: {len(state.messages)} -> {len(filtered_messages)} msgs"
            )
            state.messages = filtered_messages

        return await super().__call__(state, config)
