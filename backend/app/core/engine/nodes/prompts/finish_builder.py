import json
import logging
from typing import Any

from app.core.engine.state.config import ExecutionTicket
from app.utils.template import render_template

from .base_builder import BasePromptBuilder

logger = logging.getLogger(__name__)


class FinishPromptBuilder(BasePromptBuilder):
    """
    Constructs the system prompt for the Session Reviewer agent via Jinja2.
    """
    def __init__(
        self,
        current_plan: str,
        execution_ticket: ExecutionTicket | None,
        verification_status: Any | None,
        action_context: str,
        iteration_count: int = 0,
        project_id: int | None = None,
        telemetry: dict | None = None,
        metadata: dict | None = None,
        subtask_results: list | None = None,
        session_goal: str | None = None,
    ):
        self.current_plan = current_plan
        self.execution_ticket = execution_ticket
        self.verification_status = verification_status
        self.action_context = action_context
        self.iteration_count = iteration_count
        self.project_id = project_id
        self.telemetry = telemetry or {}
        self.metadata = metadata or {}
        self.subtask_results = subtask_results or []
        self.session_goal = session_goal

    def build(self) -> str:
        """Builds the STATIC Reviewer system prompt."""
        try:
            from app.core.context.manager import ContextManager
            
            ctx = ContextManager.current()
            mode = self.get_sandbox_mode()
            project_profile = self.read_project_profile(ctx.working_directory, "[FinishPrompt]")
            
            sys_info = {
                "project_concepts": ctx.metadata.get("project_concepts", ""),
                "project_profile": project_profile,
                "cwd": self.get_mapped_cwd(ctx.working_directory or ctx.metadata.get("cwd", "")),
            }
            
            template_vars = {
                "user_lang": self.get_user_lang(),
                "project_id": self.project_id,
                "iteration_count": self.iteration_count,
                "audit_context": self.action_context,
                "sys_info": sys_info,
                "sandbox_mode": mode,
            }

            return render_template("core/engine/finish.prompt.j2", **template_vars)
        except (TypeError, ValueError, RuntimeError) as e:
            logger.error(f"[FinishPromptBuilder] Template render failed: {e}")
            return (
                "You are the Session Reviewer. Please review the session and provide "
                "a concise summary of what was accomplished."
            )

    def build_audit_ticket(self) -> str:
        """Builds the DYNAMIC audit ticket to be injected as a HumanMessage."""
        plan_data = self.current_plan
        if isinstance(plan_data, str) and plan_data.strip():
            try:
                plan_data = json.loads(plan_data)
            except (json.JSONDecodeError, TypeError):
                # Fallback to original string if not valid JSON
                pass

        template_vars = {
            "iteration_count": self.iteration_count,
            "plan": plan_data,
            "session_goal": self.session_goal,
            "ticket": self.execution_ticket,
            "verification": self.verification_status,
            "metadata": self.metadata,
            "subtask_results": self.subtask_results,
            "audit_context": self.action_context,
            "telemetry": self.telemetry,
        }
        return render_template("core/engine/fragments/finish_audit_ticket.j2", **template_vars)
