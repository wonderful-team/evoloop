import asyncio
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.context import ContextManager
from app.core.engine.nodes.base import BaseAgentNode
from app.core.engine.nodes.utils.focus_file_hydrator import FocusFileHydrator
from app.core.engine.nodes.utils.skill_resolver import SkillResolver
from app.core.engine.nodes.utils.worker_result_processor import process_worker_result
from app.core.engine.prompts import WorkerPromptBuilder
from app.core.engine.routers import RoutingTarget
from app.core.engine.schemas import EngineResult
from app.core.engine.skill_hydrator import SkillHydrator
from app.core.engine.state import AgentState, StateUpdate
from app.core.tools.manager import tool_manager

logger = logging.getLogger(__name__)


class WorkerNode(BaseAgentNode):
    """
    The Universal Worker Node (v5.0).

    A neutral, ephemeral executor that acquires expertise dynamically at runtime
    through Skill SOPs and tool injection via the ExecutionTicket.
    """

    def __init__(self):
        super().__init__(node_name="Worker", max_steps=settings.WORKER_AGENT_MAX_STEPS)

    async def prepare_state(self, state: AgentState, config: RunnableConfig) -> StateUpdate | None:
        """Validation, ticket checks, and plan loading."""
        execution_ticket = state.blackboard.ticket
        if not execution_ticket:
            raise ValueError(
                "[WorkerNode] ExecutionTicket is missing. "
                "Supervisor must set blackboard.ticket via route_to() before routing to Worker."
            )

        if not execution_ticket.agent_config:
            raise ValueError(
                "[WorkerNode] ExecutionTicket.agent_config is missing. "
                "Supervisor must provide a valid agent_config in the ticket."
            )

        # Load plan from DB if state doesn't have one (e.g. after route_to from Supervisor)
        if not state.structured_plan and not state.current_plan:
            thread_id = config.get("configurable", {}).get("thread_id")
            if thread_id:
                try:
                    from app.infrastructure.database.resource_manager import db_resource_manager
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
                except Exception as e:
                    logger.warning(f"[Worker] Failed to load plan from DB: {e}")

        # Phase 2: Perform Scale Assessment if missing

    async def build_prompt_pair(self, state: AgentState, config: RunnableConfig) -> tuple[str, str]:
        """Construct (Static System Prompt, Dynamic Mission Message)."""
        execution_ticket = state.blackboard.ticket
        agent_config = execution_ticket.agent_config if execution_ticket else None
        blackboard = state.blackboard
        ctx = ContextManager.current()

        # Hydrate internal context
        full_plan = state.structured_plan or state.current_plan
        focus_files = await FocusFileHydrator.hydrate(execution_ticket, ctx)
        relevant_sops = list(state.relevant_sops)

        prompt_builder = WorkerPromptBuilder(
            agent_config,
            blackboard,
            skills=relevant_sops,
            ticket=execution_ticket,
            focus_files=focus_files,
            plan=full_plan
        )

        # 1. Static Instructions (Cacheable)
        static_system_prompt = await prompt_builder.build(config)

        # 2. Dynamic Mission (Turn-based context)
        from app.core.engine.prompts.utils import get_mapped_cwd
        actual_cwd = get_mapped_cwd(ctx.working_directory or ctx.metadata.get("cwd", ""))

        from app.core.environment import get_awakened_state
        awakened_state = get_awakened_state()
        telemetry: dict[str, Any] = {}
        if awakened_state:
            telemetry_snapshot = awakened_state.get_telemetry_snapshot()
            if telemetry_snapshot:
                telemetry = telemetry_snapshot.model_dump()

        mission_msg = prompt_builder.build_mission_message(
            environment_block=ctx.environment_block or "",
            cwd=actual_cwd,
            telemetry=telemetry,
            plan=full_plan,
            session_goal=state.session_goal,
        )

        return static_system_prompt, mission_msg

    async def get_tools(self, state: AgentState) -> list[Any]:
        """Load authorized tools based on ticket skills."""
        tools = await tool_manager.get_node_tools("worker", state)
        tool_names = [t.name for t in tools]
        logger.info(f"[Worker] Loaded {len(tools)} tools: {tool_names}")
        return tools

    @staticmethod
    def _build_worker_view(messages: list[BaseMessage], is_resuming: bool = False) -> list[BaseMessage]:
        """
        Build an isolated message view for Worker.

        Worker is an ephemeral executor — it only needs the starting context:
        - SystemMessage (protocol instructions)
        - User's original HumanMessage(s) (the initial request)

        All historical conversation turns (prior AIMessage, ToolMessage, old
        mission_message/context_ticket) are discarded.  The current plan state,
        task goal, focus files, and telemetry are injected fresh by
        BaseAgentNode via the latest mission_message.

        This prevents message-history bloat from prior Worker turns from
        poisoning the current ReAct loop.
        """
        result: list[BaseMessage] = []
        # Find the starting point for history if resuming (soft prune)
        # We keep SystemMessages and nameless HumanMessages regardless, 
        # but if resuming, we also keep the tail end of the conversation.
        tail_messages = []
        if is_resuming:
            # Retain the last 10 messages to preserve context during truncation recovery
            tail_messages = messages[-10:] if len(messages) >= 10 else messages

        for msg in messages:
            if isinstance(msg, SystemMessage):
                result.append(msg)
            elif isinstance(msg, HumanMessage) and not msg.name:
                # Keep only raw user inputs (no name = not a injected ticket).
                # Named HumanMessages (context_ticket, mission_message) will be
                # freshly injected by BaseAgentNode with the latest state.
                result.append(msg)
            elif is_resuming and msg in tail_messages:
                # Do not duplicate if already added
                if msg not in result:
                    result.append(msg)
            # Discard: AIMessage, ToolMessage, named HumanMessage (unless resuming and in tail)
        return result

    async def _build_fallback_outcome(
        self,
        original_state: AgentState,
        engine_result: EngineResult,
        config: RunnableConfig,
    ) -> StateUpdate:
        """Worker-specific post-processing when no signal is present."""
        execution_ticket = original_state.blackboard.ticket
        role_name = execution_ticket.agent_config.role_name if execution_ticket and execution_ticket.agent_config else "Worker"
        result = await process_worker_result(self.node_name, original_state, engine_result, execution_ticket, role_name, config=config)
        return result

    async def __call__(self, state: AgentState, config: RunnableConfig) -> StateUpdate:
        """Override to handle sequential multi-skill logic."""
        from app.core.engine.state import ensure_state
        state = ensure_state(state)

        execution_ticket = state.blackboard.ticket
        if execution_ticket:
            logger.info(
                f"[Worker] ExecutionTicket received | "
                f"topic='{execution_ticket.topic}' | "
                f"skills={execution_ticket.skill_ids or execution_ticket.skill_id} | "
                f"acceptance={execution_ticket.acceptance_criteria} | "
                f"role={(execution_ticket.agent_config.role_name if execution_ticket.agent_config else 'Worker')}"
            )

        # Check for multi-skill workflow
        skill_ids = execution_ticket.skill_ids or [] if execution_ticket else []
        workflow_mode = execution_ticket.workflow_mode or "single" if execution_ticket else "single"

        # Backward compatibility
        if not skill_ids and execution_ticket and execution_ticket.skill_id:
            skill_ids = [execution_ticket.skill_id]
            workflow_mode = "single"

        is_multi_skill_workflow = workflow_mode == "sequential" and len(skill_ids) > 1

        # Hydrate SOPs (Load early for both modes)
        if is_multi_skill_workflow:
            relevant_sops = await SkillResolver.load_skills_by_ids(skill_ids)
        else:
            relevant_sops = await SkillHydrator.get_node_skills(state, "worker")

        relevant_sops = await SkillResolver.inject_fallback_sops(relevant_sops, config)
        state.relevant_sops = relevant_sops

        # Status Emission
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
        role_name = execution_ticket.agent_config.role_name if execution_ticket and execution_ticket.agent_config else "Worker"
        task_label = role_name
        if execution_ticket and execution_ticket.topic:
            task_label = f"{role_name}: {execution_ticket.topic}"

        from app.core.monitoring.activity import activity_monitor
        await activity_monitor.update_agent_state(
            thread_id=thread_id,
            mode="EXECUTING",
            task_name=task_label,
            task_status="Initializing..."
        )

        if is_multi_skill_workflow:
            logger.info(f"[Worker] 🔄 Delegating to sequential workflow with {len(skill_ids)} skills...")
            # Initialize workflow state and route to SequentialWorkflowNode
            blackboard = state.blackboard
            blackboard.workflow_plan = relevant_sops
            blackboard.workflow_step_index = 0
            blackboard.workflow_results = []
            return StateUpdate(
                messages=[AIMessage(content=f"Starting sequential workflow with {len(skill_ids)} skills.")],
                next_node=RoutingTarget.SEQUENTIAL_WORKFLOW,
                blackboard=blackboard,
            )

        # Build isolated worker view: discard all historical conversation turns.
        # The mission_message (injected by BaseAgentNode) carries the full plan
        # state, task goal, and focus files — no need to inherit prior tool chains.
        is_resuming = execution_ticket.is_resuming if execution_ticket else False
        filtered_messages = self._build_worker_view(list(state.messages), is_resuming=is_resuming)
        if len(filtered_messages) < len(state.messages):
            logger.info(
                f"[Worker] Message view built: {len(state.messages)} -> {len(filtered_messages)} msgs "
                f"(dropped={len(state.messages) - len(filtered_messages)} historical)"
            )
            state = state.model_copy(update={"messages": filtered_messages})

        return await super().__call__(state, config)
