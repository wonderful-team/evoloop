"""
Supervisor Prompt Builder

Constructs the system prompt for the Supervisor ReAct Agent.
Allows for dynamic context injection and potential LLM-specific adaptations.
"""

import json
import logging
import os

from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.infrastructure.config.service import SystemConfigService

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

    def build(self, config: RunnableConfig) -> str:
        """Constructs the full system prompt using Jinja2 templating."""
        from jinja2 import Environment, FileSystemLoader
        from app.core.context import ContextManager

        # 1. Prepare Environment & State
        user_lang = SystemConfigService.get_language_preference()
        ctx = ContextManager.current()
        cwd = ctx.metadata.get("cwd", "")
        project_concepts = ctx.metadata.get("project_concepts", "")

        # 2. Extract raw data for template
        scratchpad = self.context.get("scratchpad", {})
        visited_nodes = scratchpad.get("visited_nodes", [])
        last_route = scratchpad.get("last_supervisor_route")
        last_human_msg = self.context.get("last_human_msg", "")
        
        active_plan_data = self.context.get("structured_plan")
        if isinstance(active_plan_data, str):
            try:
                active_plan_data = json.loads(active_plan_data)
            except Exception:
                active_plan_data = None

        # 3. Protocol & Sys Info Prep
        if cwd:
            project_structure_stub = f"CWD: {cwd}\n(Use 'get_workspace_tree' to examine files if needed)"
        else:
            project_structure_stub = "CWD: None (No Local Workspace Attached)\n(You are operating in a universal context. Do NOT assume local files exist unless specified by the user.)"

        # 4. Prepare Template Variables
        template_vars = {
            "project_id": self.project_id,
            "iteration_count": self.iteration_count,
            "user_lang": user_lang,
            "environment_block": ctx.environment_block,
            "blackboard": {
                "ticket": self.context.get("execution_ticket"),
                "verification": self.context.get("verification_status"),
                "route_reason": scratchpad.get("route_reason"),
            },
            "memory": {
                "episodic_raw": ctx.metadata.get("episodic_memory_raw", ""),
                "core_raw": ctx.metadata.get("core_memory_raw", ""),
                "use_neo4j": settings.USE_NEO4J_MEMORY,
            },
            "plan": active_plan_data,
            "plan_approved": scratchpad.get("plan_approved", False),
            "warnings": {
                "visited_nodes": visited_nodes,
                "last_route": last_route,
                "is_ambiguous": last_human_msg and len(last_human_msg.strip()) < 5,
                "last_human_msg": last_human_msg,
            },
            "sys_info": {
                "project_structure": project_structure_stub,
                "project_concepts": project_concepts,
            },
            "has_android": ctx.metadata.get("has_android", False),
            "has_macos": ctx.metadata.get("has_macos", False),
            "is_fallback_recovery": config.get("metadata", {}).get("is_fallback_recovery", False),
            "original_skill_id": config.get("metadata", {}).get("original_skill_id"),
        }

        # 5. Render Template
        try:
            template_dir = os.path.join(os.path.dirname(__file__), "templates")
            env = Environment(loader=FileSystemLoader(template_dir))
            template = env.get_template("supervisor.prompt.j2")
            return template.render(**template_vars)
        except Exception as e:
            logger.error(f"Failed to render Supervisor template: {e}")
            return f"You are the Supervisor. Error loading template: {e}\nProject ID: {self.project_id}"
