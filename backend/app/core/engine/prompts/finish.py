import json
import logging

from app.core.config import settings
from app.core.context import ContextManager
from app.core.engine.state.blackboard import BlackboardState, VerificationStatus
from app.core.engine.state.config import ExecutionTicket
from app.infrastructure.config.service import SystemConfigService
from app.utils import ControllerResponse, render_template

logger = logging.getLogger(__name__)


class FinishPromptBuilder:
    """
    Constructs the system prompt for the Session Reviewer agent via Jinja2.
    """
    def __init__(
        self,
        current_plan: str,
        execution_ticket: ExecutionTicket | None,
        verification_status: VerificationStatus | None,
        action_context: str,
        iteration_count: int = 0,
        project_id: int | None = None,
        telemetry: dict | None = None,
        blackboard: BlackboardState | None = None,
        session_goal: str | None = None,
    ):
        self.current_plan = current_plan
        self.execution_ticket = execution_ticket
        self.verification_status = verification_status
        self.action_context = action_context
        self.iteration_count = iteration_count
        self.project_id = project_id
        self.telemetry = telemetry or {}
        self.blackboard = blackboard or BlackboardState()
        self.session_goal = session_goal

    def _prepare_common_context(self) -> tuple:
        """Shared context preparation for both static prompt and dynamic audit ticket."""
        ctx = ContextManager.current()
        from .utils import get_mapped_cwd, get_sandbox_mode
        actual_cwd = get_mapped_cwd(ctx.working_directory or ctx.metadata.get("cwd", ""))
        mode = get_sandbox_mode()
        project_concepts = ctx.metadata.get("project_concepts", "")

        excluded_keys = {
            "active_skills", "project_concepts", "cwd", "episodic_memory_raw",
            "core_memory_raw", "sys_info", "is_global_mode", "has_macos", "has_android"
        }
        sanitized_metadata = {k: v for k, v in ctx.metadata.items() if k not in excluded_keys}

        return ctx, actual_cwd, mode, project_concepts, sanitized_metadata

    def build(self) -> str:
        """Builds the STATIC Reviewer system prompt."""
        ctx, actual_cwd, mode, project_concepts, sanitized_metadata = self._prepare_common_context()

        is_global_mode = self.project_id == 0 or self.project_id is None
        template_vars = {
            "user_lang": SystemConfigService.get_language_preference(),
            "project_id": self.project_id,
            "iteration_count": self.iteration_count,
            "sandbox_mode": mode,
            "sys_info": {
                "cwd": actual_cwd,
                "project_concepts": project_concepts,
                "is_global_mode": is_global_mode,
            },
            "audit_context": self.action_context
        }

        return render_template("core/engine/finish.prompt.j2", **template_vars)

    def build_audit_ticket(self) -> str:
        """Builds the DYNAMIC audit ticket to be injected as a HumanMessage."""
        ctx, actual_cwd, mode, project_concepts, sanitized_metadata = self._prepare_common_context()

        plan_data = self.current_plan
        if isinstance(plan_data, str):
            try:
                plan_data = json.loads(plan_data)
            except Exception:
                pass

        template_vars = {
            "iteration_count": self.iteration_count,
            "plan": plan_data,
            "session_goal": self.session_goal,
            "blackboard": {
                "ticket": self.execution_ticket,
                "verification": self.verification_status,
                "metadata": sanitized_metadata,
                "subtask_results": self.blackboard.subtask_results if self.blackboard else [],
            },
            "memory": {
                "episodic_raw": ctx.metadata.get("episodic_memory_raw", ""),
                "core_raw": ctx.metadata.get("core_memory_raw", ""),
            },
            "audit_context": self.action_context,
            "telemetry": self.telemetry,
        }

        return render_template("core/engine/fragments/finish_audit_ticket.j2", **template_vars)
    def build_standard_prompt(self, last_content: str, tool_usage: list[str]) -> str:
        """Builds the lightweight standard audit prompt."""
        template_vars = {
            "blackboard": {
                "ticket": self.execution_ticket,
            },
            "tools": tool_usage,
            "last_content": last_content,
        }
        return render_template("core/engine/standard_audit.prompt.j2", **template_vars)
