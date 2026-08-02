"""
Supervisor Prompt Builder

Constructs the system prompt for the Supervisor ReAct Agent.
Allows for dynamic context injection and potential LLM-specific adaptations.

The Supervisor owns skill ROUTING — it sees a lightweight skill index (name + desc)
in its static system prompt and uses read_skill_sop / route_to to dispatch the
selected skill_ids to Workers. Workers receive the full skill content downstream.
"""

import json
import logging
from typing import Any

from app.core.config import settings
from app.core.engine.schemas import SupervisorContext
from app.infrastructure.config.service import SystemConfigService
from app.utils.template import render_template

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

    async def build(self, config: Any = None) -> str:
        """Constructs the STATIC system prompt using Jinja2 templating + PromptAssemblyBuilder.

        The Jinja2 template renders the static role/protocol.
        PromptAssemblyBuilder appends a lightweight skills index so the Supervisor
        can route tasks to the right skill without loading full SKILL.md content —
        it uses read_skill_sop to inspect details only when needed (NLP Skill Loading).
        """
        from app.core.context import ContextManager, plugin_registry

        # 1. Prepare Environment
        ctx = ContextManager.current()
        await plugin_registry.ahydrate_context(ctx)
        user_lang = self.get_user_lang()
        actual_cwd = self.get_mapped_cwd(ctx.working_directory or ctx.metadata.get("cwd", ""))
        mode = self.get_sandbox_mode()

        # 2. Protocol & Sys Info Prep (STATIC parts only)
        project_profile = self.read_project_profile(ctx.working_directory, "[SupervisorPrompt]")

        # 3. Prepare Template Variables (STATIC only — no blackboard/memory/telemetry)
        is_voice = ctx.metadata.get("source") == "voice"
        has_running_worker = ctx.metadata.get("has_running_worker") == "true"
        running_worker_desc = ctx.metadata.get("running_worker_desc", "")
        lightning_mode = SystemConfigService.get_value("LIGHTNING_MODE", "none")
        is_lightning = lightning_mode not in ("none", "")
        template_vars = {
            "project_id": self.project_id,
            "user_lang": user_lang,
            "sandbox_mode": mode,
            "multi_tenant_mode": settings.MULTI_TENANT_MODE,
            "sys_info": {
                "cwd": actual_cwd,
                "project_profile": project_profile,
                "wiki_index": ctx.wiki_index,
            },
            "project_concepts": ctx.metadata.get("project_concepts", ""),
            "is_supervisor": True,
            "is_voice": is_voice,
            "is_lightning": is_lightning,
            "has_running_worker": has_running_worker,
            "running_worker_desc": running_worker_desc,
            "has_file_operations": False,
            "agent_name": SystemConfigService.get_value("AGENT_NAME", "EvoLoop"),
            "agent_company": SystemConfigService.get_value("AGENT_COMPANY", "上海方天画戟信息技术有限公司"),
            "agent_website": SystemConfigService.get_value("AGENT_WEBSITE", "https://evoloop.cn"),
        }

        # 4. Render Core Template (lightning or standard)
        template = "core/engine/supervisor_lightning.prompt.j2" if is_lightning else "core/engine/supervisor.prompt.j2"
        base_prompt = render_template(template, **template_vars)

        logger.info(f"[SupervisorPrompt] 📝 Static prompt length: {len(base_prompt)} chars")

        return base_prompt

    async def build_context_ticket(self, config: Any = None, session_goal: str | None = None) -> str:
        """Constructs the dynamic CONTEXT TICKET for injection as a User Message.

        This contains per-turn state: explicit/active skills, memory snapshots,
        active plan/ticket, and a compact environment summary. By keeping this in a
        User Message (not System Prompt), the static System Prompt remains cacheable.
        """
        from app.core.context import ContextManager, plugin_registry

        ctx = ContextManager.current()
        await plugin_registry.ahydrate_context(ctx)

        state = self.context.state
        active_plan_data = self.context.structured_plan
        if isinstance(active_plan_data, str) and active_plan_data.strip():
            active_plan_data = json.loads(active_plan_data)

        env_summaries = ctx.environment_summaries or {}
        if not isinstance(env_summaries, dict):
            env_summaries = {}
        active_skills = ctx.metadata.get("active_skills", [])
        active_macros = ctx.metadata.get("active_macros", [])

        # Extract explicit skill attachment from run metadata
        run_metadata = config.get("metadata", {}) if config else {}
        explicit_skills = run_metadata.get("explicit_skills")

        template_vars = {
            "iteration_count": self.iteration_count,
            "environment_summaries": env_summaries,
            "session_goal": session_goal,
            "active_skills": active_skills,
            "active_macros": active_macros,
            "explicit_skills": explicit_skills,
            "memory": {
                "episodic_raw": ctx.metadata.get("episodic_memory_raw", ""),
                "core_raw": ctx.metadata.get("core_memory_raw", ""),
            },
            "ticket": state.ticket,
            "subtask_results": state.subtask_results,
            "verification": state.verification,
            "plan": active_plan_data,
            "plan_approved": state.plan_approved,
        }

        rendered = render_template("core/engine/fragments/supervisor_context_ticket.j2", **template_vars)
        logger.info(f"[ContextTicket] 📋 Dynamic ticket length: {len(rendered)} chars")
        return rendered
