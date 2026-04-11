"""
Supervisor Prompt Builder

Constructs the system prompt for the Supervisor ReAct Agent.
Allows for dynamic context injection and potential LLM-specific adaptations.
"""

import json
import logging

from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.environment import get_awakened_state
from app.infrastructure.config.service import SystemConfigService
from app.utils import ControllerResponse, render_template

logger = logging.getLogger(__name__)


class SupervisorPromptBuilder:
    def __init__(
        self,
        project_id: int,
        iteration_count: int,
        context: dict = None,
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
        project_concepts = ctx.metadata.get("project_concepts", "")

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
        try:
            rendered = render_template("agents/supervisor.prompt.j2", **template_vars)
            
            logger.info(f"[SupervisorPrompt] 📝 Static prompt length: {len(rendered)} chars")
            return rendered
        except Exception as e:
            logger.error(f"Failed to render Supervisor template: {e}")
            return f"TEMPLATE_ERROR: {str(e)}"

    async def build_context_ticket(self, config: RunnableConfig) -> str:
        """Constructs the dynamic CONTEXT TICKET for injection as a User Message.
        
        This contains all per-turn state: Blackboard, Memory, Environment Block,
        Active Plan, and iteration metadata. By keeping this in a User Message
        (not System Prompt), the static System Prompt remains cacheable.
        """
        from app.core.context import ContextManager, plugin_registry
        from .utils import get_mapped_cwd, get_sandbox_mode

        ctx = ContextManager.current()
        plugin_registry.hydrate_context(ctx)
        actual_cwd = get_mapped_cwd(ctx.working_directory or ctx.metadata.get("cwd", ""))
        is_global_mode = self.project_id == 0 or self.project_id is None
        
        # Get telemetry if available (trimmed)
        state = get_awakened_state()
        telemetry_data = {}
        MAX_INSTALLED_APPS = 10
        try:
            if state:
                telemetry_data = state.get_telemetry_snapshot()
                if "macos" in telemetry_data and "installed_apps" in telemetry_data["macos"]:
                    original = len(telemetry_data["macos"]["installed_apps"])
                    telemetry_data["macos"]["installed_apps"] = telemetry_data["macos"]["installed_apps"][:MAX_INSTALLED_APPS]
                    if original > MAX_INSTALLED_APPS:
                        logger.debug(f"[ContextTicket] Pruned macOS apps {original} → {MAX_INSTALLED_APPS}")
        except Exception as e:
            logger.warning(f"[ContextTicket] Failed to fetch telemetry: {e}")

        blackboard = self.context.get("blackboard", {}) if self.context else {}
        active_plan_data = self.context.get("structured_plan")
        if isinstance(active_plan_data, str):
            try:
                import json
                active_plan_data = json.loads(active_plan_data)
            except Exception:
                active_plan_data = None

        env_block = ctx.environment_block or ""
        topic = (blackboard.get("ticket", {}).get("topic") or "")

        template_vars = {
            "iteration_count": self.iteration_count,
            "project_id": self.project_id,
            "cwd": actual_cwd,
            "is_global_mode": is_global_mode,
            "environment_block": env_block,
            "memory": {
                "episodic_raw": ctx.metadata.get("episodic_memory_raw", ""),
                "core_raw": ctx.metadata.get("core_memory_raw", ""),
            },
            "blackboard": {
                "ticket": blackboard.get("ticket"),
                "subtask_results": blackboard.get("subtask_results", []),
                "visited_nodes": blackboard.get("visited_nodes", []),
                "verification": blackboard.get("verification"),
                "metadata": blackboard.get("metadata", {}),
            },
            "plan": active_plan_data,
            "plan_approved": blackboard.get("plan_approved", False),
            "project_concepts": ctx.metadata.get("project_concepts", ""),
            "active_skills": [
                {"id": s.get("id"), "name": s.get("name"), "namespace": s.get("namespace", "default")} 
                for s in ctx.metadata.get("active_skills", [])
            ],
        }

        try:
            rendered = render_template("fragments/supervisor_context_ticket.j2", **template_vars)
            logger.info(f"[ContextTicket] 📋 Dynamic ticket length: {len(rendered)} chars")
            return rendered
        except Exception as e:
            logger.error(f"Failed to render Context Ticket: {e}")
            return f"[CONTEXT UPDATE — Turn {self.iteration_count}] (render error: {e})"
