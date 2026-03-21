import logging
from app.infrastructure.config.service import SystemConfigService
from app.constants import TECHNICAL_MARKERS, STATUS_ICONS
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
        action_context: str
    ):
        self.current_plan = current_plan
        self.execution_ticket = execution_ticket
        self.verification_status = verification_status
        self.action_context = action_context

    def build(self) -> str:
        """
        Builds the final Reviewer system prompt via Jinja2.
        """
        template_vars = {
            "user_lang": SystemConfigService.get_language_preference(),
            "blackboard": {
                "ticket": self.execution_ticket,
                "verification": self.verification_status,
            },
            "audit_context": self.action_context,
            "technical_markers": ", ".join(TECHNICAL_MARKERS),
            "icons": {
                "success": STATUS_ICONS["success"],
                "failed": STATUS_ICONS["failed"]
            }
        }

        try:
            return render_template("agents/finish.prompt.j2", **template_vars)
        except Exception as e:
            logger.error(f"Error rendering Reviewer template: {e}")
            return ControllerResponse.error(
                "Session Reviewer template error",
                details=str(e)
            )
