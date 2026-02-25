import os
import logging
from jinja2 import Environment, FileSystemLoader
from app.infrastructure.config.service import SystemConfigService

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

        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.env = Environment(loader=FileSystemLoader(template_dir))

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
        }

        try:
            template = self.env.get_template("finish.prompt.j2")
            return template.render(**template_vars)
        except Exception as e:
            logger.error(f"Error rendering Reviewer template: {e}")
            return f"You are the Session Reviewer. Error loading template: {e}"
