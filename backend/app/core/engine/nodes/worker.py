import logging
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.context import ContextManager
from app.core.engine.context_monitor import ContextMonitor
from app.core.engine.schemas import EngineResult
from app.core.engine.nodes.base import BaseAgentNode
from app.core.engine.nodes.utils.focus_file_hydrator import FocusFileHydrator
from app.core.engine.nodes.utils.skill_resolver import SkillResolver
from app.core.engine.nodes.utils.worker_result_processor import process_worker_result
from app.core.engine.prompts import WorkerPromptBuilder
from app.core.engine.routers import RoutingTarget
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
        """Validation and ticket checks."""
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

        return None

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
        all_messages = list(state.messages)
        model = config.get("configurable", {}).get("model")
        context_stats = ContextMonitor.calculate(all_messages, model=model).to_prompt()

        from app.core.engine.prompts.utils import get_mapped_cwd
        actual_cwd = get_mapped_cwd(ctx.working_directory or ctx.metadata.get("cwd", ""))

        from app.core.environment import get_awakened_state
        awakened = get_awakened_state()
        telemetry = awakened.get_telemetry_snapshot() if awakened else {}

        mission_msg = prompt_builder.build_mission_message(
            context_stats=context_stats,
            environment_block=ctx.environment_block or "",
            cwd=actual_cwd,
            telemetry=telemetry,
            plan=full_plan,
            session_goal=state.session_goal,
        )

        return static_system_prompt, mission_msg

    async def get_tools(self, state: AgentState) -> list[Any]:
        """Load authorized tools based on ticket skills."""
        return await tool_manager.get_node_tools("worker", state)

    async def _build_fallback_outcome(
        self,
        original_state: AgentState,
        engine_result: EngineResult,
        config: RunnableConfig,
    ) -> StateUpdate:
        """Worker-specific post-processing when no signal is present."""
        execution_ticket = original_state.blackboard.ticket
        role_name = execution_ticket.agent_config.role_name if execution_ticket and execution_ticket.agent_config else "Worker"
        result = process_worker_result(self.node_name, original_state, engine_result, execution_ticket, role_name)
        return result

    async def __call__(self, state: AgentState, config: RunnableConfig) -> StateUpdate:
        """Override to handle sequential multi-skill logic."""
        # ensure_state is already called in BaseAgentNode.__call__;
        execution_ticket = state.blackboard.ticket

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

        # Standard ReAct loop (Delegated to BaseAgentNode)
        return await super().__call__(state, config)
