import logging
from app.infrastructure.config.service import SystemConfigService

from app.core.config import settings
from app.core.context import ContextManager
from app.utils import ControllerResponse, render_template

logger = logging.getLogger(__name__)


class FinishPromptBuilder:
    """
    Constructs the system prompt for the Session Reviewer agent via Jinja2.
    """
    def __init__(
        self,
        current_plan: str,
        execution_ticket: dict | None,
        verification_status: dict | None,
        action_context: str,
        iteration_count: int = 0,
        project_id: int | None = None,
        telemetry: dict | None = None,
        blackboard: dict | None = None
    ):
        self.current_plan = current_plan
        self.execution_ticket = execution_ticket
        self.verification_status = verification_status
        self.action_context = action_context
        self.iteration_count = iteration_count
        self.project_id = project_id
        self.telemetry = telemetry or {}
        self.blackboard = blackboard or {}

    def build(self) -> str:
        """
        Builds the final Reviewer system prompt via Jinja2.
        """
        ctx = ContextManager.current()
        from .utils import get_mapped_cwd, get_sandbox_mode
        actual_cwd = get_mapped_cwd(ctx.working_directory or ctx.metadata.get("cwd", ""))
        mode = get_sandbox_mode()
        project_concepts = ctx.metadata.get("project_concepts", "")

        # Metadata Filtering (Pollution Control)
        # We exclude large system-level objects and redundant keys that are handled explicitly below
        excluded_keys = {
            "active_skills", "project_concepts", "cwd", "episodic_memory_raw", 
            "core_memory_raw", "sys_info", "is_global_mode", "has_macos", "has_android"
        }
        sanitized_metadata = {k: v for k, v in ctx.metadata.items() if k not in excluded_keys}

        template_vars = {
            "user_lang": SystemConfigService.get_language_preference(),
            "project_id": self.project_id,
            "iteration_count": self.iteration_count,
            "telemetry": self.telemetry,
            "sandbox_mode": mode,
            "plan": self.current_plan,
            "blackboard": {
                "ticket": self.execution_ticket,
                "verification": self.verification_status,
                "metadata": sanitized_metadata,
                "subtask_results": self.blackboard.get("subtask_results", []),
            },
            "sys_info": {
                "cwd": actual_cwd,
                "project_concepts": project_concepts,
            },
            "memory": {
                "episodic_raw": ctx.metadata.get("episodic_memory_raw", ""),
                "core_raw": ctx.metadata.get("core_memory_raw", ""),
                "use_neo4j": settings.USE_NEO4J_MEMORY,
            },
            "audit_context": self.action_context
        }

        try:
            return render_template("agents/finish.prompt.j2", **template_vars)
        except Exception as e:
            logger.error(f"Error rendering Reviewer template: {e}")
            return ControllerResponse.error(
                "Session Reviewer template error",
                details=str(e)
            )
