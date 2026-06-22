"""
Supervisor Prompt Builder

Constructs the system prompt for the Supervisor ReAct Agent.
Allows for dynamic context injection and potential LLM-specific adaptations.
"""
import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.tools.registry import get_tool_bundle
from app.core.engine.schemas import SupervisorContext
from app.infrastructure.config.service import SystemConfigService
from app.utils import render_template

from .base_builder import BasePromptBuilder

logger = logging.getLogger(__name__)


class SupervisorPromptBuilder(BasePromptBuilder):
    def __init__(
        self,
        project_id: int,
        iteration_count: int,
        context: SupervisorContext,
    ):
        self.project_id = project_id
        self.iteration_count = iteration_count
        self.context: Any = context or {}

    async def build(self, config: RunnableConfig = None) -> str:
        """Constructs the STATIC system prompt using Jinja2 templating.

        Dynamic per-turn state (Blackboard, Memory, Environment, Active Plan)
        is now separated into build_context_ticket() which is injected as a
        User Message prefix — this makes the System Prompt cacheable.
        """
        from app.core.context import ContextManager, plugin_registry

        # 1. Prepare Environment
        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)
        user_lang = self.get_user_lang()
        actual_cwd = self.get_mapped_cwd(ctx.working_directory or ctx.metadata.get("cwd", ""))
        mode = self.get_sandbox_mode()

        # 2. Protocol & Sys Info Prep (STATIC parts only)

        # Read PROJECT.md if exists (static for the session)
        project_profile = self.read_project_profile(ctx.working_directory, "[SupervisorPrompt]")

        # 3. Prepare Template Variables (STATIC only — no blackboard/memory/telemetry)
        template_vars = {
            "project_id": self.project_id,
            "user_lang": user_lang,
            "sandbox_mode": mode,
            "multi_tenant_mode": settings.MULTI_TENANT_MODE,
            "sys_info": {
                "cwd": actual_cwd,
                "project_profile": project_profile,
            },
            "project_concepts": ctx.metadata.get("project_concepts", ""),
            "is_supervisor": True,
            "has_file_operations": False,
            "agent_name": SystemConfigService.get_value("AGENT_NAME", "EvoLoop"),
            "agent_company": SystemConfigService.get_value("AGENT_COMPANY", "上海方天画戟信息技术有限公司"),
            "agent_website": SystemConfigService.get_value("AGENT_WEBSITE", "https://evoloop.cn"),
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

        state = self.context.state
        active_plan_data = self.context.structured_plan
        if isinstance(active_plan_data, str) and active_plan_data.strip():
            active_plan_data = json.loads(active_plan_data)

        env_block = ctx.environment_block or ""
        active_skills = ctx.metadata.get("active_skills", [])

        # Extract explicit skill attachment from run metadata
        run_metadata = config.get("metadata", {}) if config else {}
        explicit_skills = run_metadata.get("explicit_skills")

        # Collect dynamic metadata from flat state
        metadata_fields = {
            "tool_history": state.tool_history,
            "pending_approvals": [x.model_dump() if hasattr(x, "model_dump") else x for x in (state.pending_approvals or [])],
            "audit_anomalies": [x.model_dump() if hasattr(x, "model_dump") else x for x in (state.audit_anomalies or [])],
            "tool_memory": state.tool_memory,
            "final_outcome": state.final_outcome,
            "shadow_audit": state.shadow_audit,
            "termination_outcome": state.termination_outcome,
            "last_aggregation_result": state.last_aggregation_result,
            "audit_tier": state.audit_tier,
            "audit_meta": state.audit_meta.model_dump() if hasattr(state.audit_meta, "model_dump") and state.audit_meta else state.audit_meta,
            "blocked_by_hook": state.blocked_by_hook,
            "plan_progress": state.plan_progress.model_dump() if hasattr(state.plan_progress, "model_dump") and state.plan_progress else state.plan_progress,
            "max_supervisor_steps": state.max_supervisor_steps,
            "audit_input_data": state.audit_input_data.model_dump() if hasattr(state.audit_input_data, "model_dump") and state.audit_input_data else state.audit_input_data,
            "force_comprehensive_audit": state.force_comprehensive_audit,
        }
        metadata_clean = {k: v for k, v in metadata_fields.items() if v is not None}

        template_vars = {
            "iteration_count": self.iteration_count,
            "environment_block": env_block,
            "session_goal": session_goal,
            "active_skills": active_skills,
            "explicit_skills": explicit_skills,
            "memory": {
                "episodic_raw": ctx.metadata.get("episodic_memory_raw", ""),
                "core_raw": ctx.metadata.get("core_memory_raw", ""),
            },
            "ticket": state.ticket,
            "subtask_results": state.subtask_results,
            "visited_nodes": state.visited_nodes,
            "verification": state.verification,
            "metadata": metadata_clean,
            "plan": active_plan_data,
            "plan_approved": state.plan_approved,
        }

        rendered = render_template("core/engine/fragments/supervisor_context_ticket.j2", **template_vars)
        logger.info(f"[ContextTicket] 📋 Dynamic ticket length: {len(rendered)} chars")
        return rendered
