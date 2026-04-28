"""
Supervisor Prompt Builder

Constructs the system prompt for the Supervisor ReAct Agent.
Allows for dynamic context injection and potential LLM-specific adaptations.
"""
import json
import logging

from langchain_core.runnables import RunnableConfig

from app.core.engine.schemas import SupervisorContext
from app.infrastructure.config.service import SystemConfigService
from app.utils import render_template

logger = logging.getLogger(__name__)


class SupervisorPromptBuilder:
    def __init__(
        self,
        project_id: int,
        iteration_count: int,
        context: SupervisorContext,
    ):
        self.project_id = project_id
        self.iteration_count = iteration_count
        self.context = context or {}

    async def build(self, config: RunnableConfig) -> str:
        """Constructs the STATIC system prompt using Jinja2 templating.
        
        Dynamic per-turn state (Blackboard, Memory, Environment, Active Plan)
        is now separated into build_context_ticket() which is injected as a
        User Message prefix — this makes the System Prompt cacheable.
        """
        from app.core.context import ContextManager, plugin_registry

        from .utils import get_mapped_cwd, get_sandbox_mode

        # 1. Prepare Environment
        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)
        user_lang = SystemConfigService.get_language_preference()
        actual_cwd = get_mapped_cwd(ctx.working_directory or ctx.metadata.get("cwd", ""))
        mode = get_sandbox_mode()

        # 2. Protocol & Sys Info Prep (STATIC parts only)
        is_global_mode = self.project_id == 0 or self.project_id is None

        # 3. Prepare Template Variables (STATIC only — no blackboard/memory/telemetry)
        template_vars = {
            "project_id": self.project_id,
            "user_lang": user_lang,
            "sandbox_mode": mode,
            "sys_info": {
                "cwd": actual_cwd,
                "is_global_mode": is_global_mode,
            },
            # Keep static references but NOT the per-turn dynamic data
        }

        # 4. Render Template
        rendered = render_template("core/engine/supervisor.prompt.j2", **template_vars)
        logger.info(f"[SupervisorPrompt] 📝 Static prompt length: {len(rendered)} chars")
        return rendered

    async def build_context_ticket(self, config: RunnableConfig, session_goal: str | None = None) -> str:
        """Constructs the dynamic CONTEXT TICKET for injection as a User Message.
        
        This contains all per-turn state: Blackboard, Memory, Environment Block,
        Active Plan, and iteration metadata. By keeping this in a User Message
        (not System Prompt), the static System Prompt remains cacheable.
        """
        from app.core.context import ContextManager, plugin_registry

        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)

        blackboard = self.context.blackboard
        active_plan_data = self.context.structured_plan
        if isinstance(active_plan_data, str) and active_plan_data.strip():
            active_plan_data = json.loads(active_plan_data)

        env_block = ctx.environment_block or ""
        active_skills = ctx.metadata.get("active_skills", [])

        # Extract explicit skill attachment from run metadata
        run_metadata = config.get("metadata", {}) if config else {}
        explicit_skill_id = run_metadata.get("explicit_skill_id")
        explicit_skill_name = run_metadata.get("explicit_skill_name")

        template_vars = {
            "iteration_count": self.iteration_count,
            "environment_block": env_block,
            "session_goal": session_goal,
            "active_skills": active_skills,
            "explicit_skill": {
                "id": explicit_skill_id,
                "name": explicit_skill_name,
            } if explicit_skill_id else None,
            "memory": {
                "episodic_raw": ctx.metadata.get("episodic_memory_raw", ""),
                "core_raw": ctx.metadata.get("core_memory_raw", ""),
            },
            "blackboard": {
                "ticket": blackboard.ticket,
                "subtask_results": blackboard.subtask_results,
                "visited_nodes": blackboard.visited_nodes,
                "verification": blackboard.verification,
                "metadata": blackboard.metadata.model_dump(),
            },
            "plan": active_plan_data,
            "plan_approved": blackboard.plan_approved,
        }

        rendered = render_template("core/engine/fragments/supervisor_context_ticket.j2", **template_vars)
        logger.info(f"[ContextTicket] 📋 Dynamic ticket length: {len(rendered)} chars")
        return rendered
