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
from app.core.environment import get_awakened_state
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

    async def build(self, config: RunnableConfig) -> str:
        """Constructs the full system prompt using Jinja2 templating."""
        from jinja2 import Environment, FileSystemLoader
        from app.core.context import ContextManager

        # 1. Prepare Environment & State
        user_lang = SystemConfigService.get_language_preference()
        ctx = ContextManager.current()
        cwd = ctx.metadata.get("cwd", "")
        project_concepts = ctx.metadata.get("project_concepts", "")

        # Get the current awakened state for telemetry access
        state = get_awakened_state()

        # 2. Extract raw data for template (Phase 1: Unified Blackboard)
        # Phase 4: Blackboard Integration
        # Blackboard comes from graph context, not awakened state
        blackboard = self.context.get("blackboard", {}) if self.context else {}
        visited_nodes = blackboard.get("visited_nodes", [])
        last_route = blackboard.get("route_reason")

        context = {
            "current_plan": self.context.get("current_plan") if self.context else None,
            "execution_ticket": blackboard.get("ticket"),
            "verification_status": blackboard.get("verification"),
            "visited_nodes": visited_nodes,
            "last_route": last_route,
            "subtask_results": blackboard.get("subtask_results", []),
            "plan_approved": blackboard.get("plan_approved", False),
        }

        last_human_msg = self.context.get("last_human_msg", "")
        
        active_plan_data = self.context.get("structured_plan")
        if isinstance(active_plan_data, str):
            try:
                active_plan_data = json.loads(active_plan_data)
            except Exception:
                active_plan_data = None

        # 3. Protocol & Sys Info Prep
        is_global_mode = self.project_id == 0 or self.project_id is None
        if cwd:
            project_structure_stub = f"CWD: {cwd}\n(Use 'get_workspace_tree' to examine files if needed)"
        else:
            if is_global_mode:
                project_structure_stub = "CWD: None (GLOBAL MODE ACTIVE)\n(You are NOT currently operating within a specific project. For security, standard file operations (read/write/edit) are DISABLED in this mode. If you need to manipulate local files, please use the 'chat' node to ask the user to switch to a target project.)"
            else:
                project_structure_stub = "CWD: None (No Local Workspace Attached)\n(You are operating in a universal context. Do NOT assume local files exist unless specified by the user.)"

        # 3.1 Fetch Telemetry (Sensors)
        telemetry_data = {}
        try:
            if state:
                # Raw status (not pre-rendered text)
                telemetry_data = {
                    "android": [{"id": d.device_id, "reachable": d.is_reachable} for d in state.android_devices],
                    "macos": bool(state.macos),
                    "network": state.network.internet_connected if state.network else False
                }
        except Exception as e:
            logger.warning(f"[SupervisorPrompt] Failed to fetch telemetry: {e}")

        # 3.2 Prepare Template Variables
        template_vars = {
            "project_id": self.project_id,
            "iteration_count": self.iteration_count,
            "user_lang": user_lang,
            "telemetry": telemetry_data,  # <--- NEW: Raw Sensors
            "blackboard": {
                "ticket": blackboard.get("ticket"),
                "verification": blackboard.get("verification"),
                "route_reason": blackboard.get("route_reason"),
                "metadata": blackboard.get("metadata", {}),
                "subtask_results": blackboard.get("subtask_results", []),
            },
            "memory": {
                "episodic_raw": ctx.metadata.get("episodic_memory_raw", ""),
                "core_raw": ctx.metadata.get("core_memory_raw", ""),
                "use_neo4j": settings.USE_NEO4J_MEMORY,
            },
            "plan": active_plan_data,
            "plan_approved": blackboard.get("plan_approved", False),
            "warnings": {
                "visited_nodes": visited_nodes,
                "last_route": last_route,
                "last_human_msg": last_human_msg,
            },
            "sys_info": {
                "project_structure": project_structure_stub,
                "project_concepts": project_concepts,
                "active_skills": ctx.metadata.get("active_skills", []),
            },
            "has_android": telemetry_data.get("android", []),
            "has_macos": telemetry_data.get("macos", False),
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
