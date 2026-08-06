"""Skill execution response formatting utilities.

Formats skill/macro success, failure and cancellation responses into
prompt-ready strings for the agent.
"""

from typing import Any

from app.utils.controller_response import ControllerResponse
from app.utils.template import render_template


class SkillResponse:
    """
    Utility class for formatting skill response messages.

    Usage:
        from app.core.execution.skill_response import SkillResponse

        return SkillResponse.success("skill_name", extracted_data={...})
        return SkillResponse.error("skill_name", "error message")
    """

    @staticmethod
    def success(skill_name: str, extracted_data: dict[str, Any] | None = None) -> str:
        """Render a skill success response."""
        details = None
        if extracted_data:
            details = render_template("core/vision/perceptions.prompt.j2", extracted_data=extracted_data)

        return ControllerResponse.success(message=f"Skill '{skill_name}' completed", details=details)

    @staticmethod
    def error(
        skill_name: str,
        message: str,
        fallback_context: dict[str, Any] | None = None,
        suggestions: list | None = None,
    ) -> str:
        """Render a skill error response with optional fallback details."""
        details = None
        if fallback_context:
            failed_step = fallback_context.get("failed_step", {})
            error_message = fallback_context.get("error_message", message)
            details = render_template(
                "common/events/skill_error_details.prompt.j2",
                failed_step=failed_step,
                error_message=error_message,
                suggestions=suggestions or [],
            )

        return ControllerResponse.error(message=f"Skill '{skill_name}' failed: {message}", details=details)

    @staticmethod
    def cancelled(skill_name: str, reason: str | None = None) -> str:
        """Render a skill cancellation response."""
        msg = f"Skill '{skill_name}' was cancelled"
        if reason:
            msg += f": {reason}"
        return ControllerResponse.error(message=msg)
