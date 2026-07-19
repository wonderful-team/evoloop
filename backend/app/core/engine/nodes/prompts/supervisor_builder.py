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
from app.core.engine.prompts import PromptAssemblyBuilder
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
        plugin_registry.hydrate_context(ctx)
        user_lang = self.get_user_lang()
        actual_cwd = self.get_mapped_cwd(ctx.working_directory or ctx.metadata.get("cwd", ""))
        mode = self.get_sandbox_mode()

        # 2. Protocol & Sys Info Prep (STATIC parts only)
        project_profile = self.read_project_profile(ctx.working_directory, "[SupervisorPrompt]")

        # Read wiki index for prompt injection (project mode only)
        from app.core.engine.nodes.utils.node_utils import read_wiki_index

        wiki_index = await read_wiki_index(ctx.project_id)

        # 3. Prepare Template Variables (STATIC only — no blackboard/memory/telemetry)
        is_voice = ctx.metadata.get("source") == "voice"
        template_vars = {
            "project_id": self.project_id,
            "user_lang": user_lang,
            "sandbox_mode": mode,
            "multi_tenant_mode": settings.MULTI_TENANT_MODE,
            "sys_info": {
                "cwd": actual_cwd,
                "project_profile": project_profile,
                "wiki_index": wiki_index,
            },
            "project_concepts": ctx.metadata.get("project_concepts", ""),
            "is_supervisor": True,
            "is_voice": is_voice,
            "has_file_operations": False,
            "agent_name": SystemConfigService.get_value("AGENT_NAME", "EvoLoop"),
            "agent_company": SystemConfigService.get_value("AGENT_COMPANY", "上海方天画戟信息技术有限公司"),
            "agent_website": SystemConfigService.get_value("AGENT_WEBSITE", "https://evoloop.cn"),
        }

        # 4. Render Core Template
        base_prompt = render_template("core/engine/supervisor.prompt.j2", **template_vars)

        # 5. Append lightweight skills index via PromptAssemblyBuilder
        # Supervisor owns routing — it only needs name+desc to decide which skill
        # to dispatch. Full SKILL.md is fetched on demand via read_skill_sop.
        skills_index = self._extract_skills_index(ctx)
        if skills_index:
            assembly = PromptAssemblyBuilder()
            assembly.add_section("core", base_prompt, priority=0)
            assembly.add_skills_index(skills_index)
            rendered = assembly.build()
        else:
            rendered = base_prompt

        logger.info(f"[SupervisorPrompt] 📝 Static prompt length: {len(rendered)} chars (skills index: {len(skills_index)} entries)")

        return rendered

    def _extract_skills_index(self, ctx: Any) -> list[dict]:
        """Extract lightweight skill metadata for the Supervisor's routing index."""
        active_skills = ctx.metadata.get("active_skills", []) or []
        index = []
        for s in active_skills:
            if isinstance(s, dict):
                index.append({
                    "id": s.get("id", ""),
                    "name": s.get("name", ""),
                    "description": s.get("description", ""),
                })
            else:
                # SkillListItem / object form
                index.append({
                    "id": getattr(s, "id", "") or "",
                    "name": getattr(s, "name", "") or "",
                    "description": getattr(s, "description", "") or "",
                })
        return index

    async def build_context_ticket(self, config: Any = None, session_goal: str | None = None) -> str:
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
        active_macros = ctx.metadata.get("active_macros", [])

        # Extract explicit skill attachment from run metadata
        run_metadata = config.get("metadata", {}) if config else {}
        explicit_skills = run_metadata.get("explicit_skills")

        # Collect dynamic metadata from flat state
        metadata_clean = state.build_metadata_dict()

        template_vars = {
            "iteration_count": self.iteration_count,
            "environment_block": env_block,
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
            "visited_nodes": state.visited_nodes,
            "verification": state.verification,
            "metadata": metadata_clean,
            "plan": active_plan_data,
            "plan_approved": state.plan_approved,
        }

        rendered = render_template("core/engine/fragments/supervisor_context_ticket.j2", **template_vars)
        logger.info(f"[ContextTicket] 📋 Dynamic ticket length: {len(rendered)} chars")
        return rendered
