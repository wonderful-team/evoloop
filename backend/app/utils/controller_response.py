"""Controller Response Utility

Provides standardized response formatting for environment controllers.
Eliminates repetitive render_template calls for report/response.prompt.j2
"""

from app.utils.template import render_template


class ControllerResponse:
    """
    Utility class for generating standardized controller responses.

    This class eliminates repetitive render_template calls across mobile,
    browser, and desktop controllers by providing convenient static methods
    for common response patterns.

    Usage:
        from app.utils.controller_response import ControllerResponse

        # Success responses
        return ControllerResponse.success("Action completed")
        return ControllerResponse.success("Tapped element", details=element_info)

        # Error responses
        return ControllerResponse.error("Failed to tap")
        return ControllerResponse.not_found("button1")
        return ControllerResponse.missing_param("element_name")

        # Custom responses
        return ControllerResponse.render(success=True, message="Custom", details=...)
    """

    @staticmethod
    def render(
        success: bool,
        message: str,
        details: str | None = None,
        note: str | None = None,
        **extra_vars,
    ):
        """
        Render a standard response template with given parameters.

        Args:
            success: Whether the operation succeeded
            message: Primary response message
            details: Optional detailed information
            note: Optional additional note
            **extra_vars: Additional template variables

        Returns:
            Rendered response string
        """
        return render_template(
            "common/report/response.prompt.j2",
            success=success,
            message=message,
            details=details,
            note=note,
            **extra_vars,
        )

    @staticmethod
    def success(message: str, details: str | None = None, note: str | None = None) -> str:
        """Render a success response."""
        return ControllerResponse.render(success=True, message=message, details=details, note=note)

    @staticmethod
    def error(message: str, details: str | None = None, note: str | None = None) -> str:
        """Render an error response."""
        return ControllerResponse.render(success=False, message=message, details=details, note=note)

    @staticmethod
    def not_found(item_name: str, item_type: str = "element") -> str:
        """Render a 'not found' error response."""
        return ControllerResponse.error(f"{item_type} '{item_name}' not found")

    @staticmethod
    def missing_param(param_name: str) -> str:
        """Render a 'missing parameter' error response."""
        return ControllerResponse.error(f"Missing required parameter: '{param_name}'")

    @staticmethod
    def invalid_param(param_name: str, reason: str | None = None) -> str:
        """Render an 'invalid parameter' error response."""
        msg = f"Invalid parameter: '{param_name}'"
        if reason:
            msg += f" ({reason})"
        return ControllerResponse.error(msg)

    @staticmethod
    def action_result(
        action: str,
        target: str | None = None,
        success: bool = True,
        details: str | None = None,
        note: str | None = None,
    ) -> str:
        """
        Render an action result response.

        Args:
            action: The action performed (e.g., "tap", "swipe", "input")
            target: The target element/location
            success: Whether the action succeeded
            details: Optional details
            note: Optional additional note or warning
        """
        if target:
            message = f"Action: {action} on '{target}'"
        else:
            message = f"Action: {action}"

        return ControllerResponse.render(success=success, message=message, details=details, note=note)

    @staticmethod
    def navigation_result(
        url: str,
        success: bool = True,
        title: str | None = None,
        details: str | None = None,
    ) -> str:
        """Render a navigation result response."""
        message = f"Navigated to: {url}"
        if title:
            note = f"Page title: {title}"
        else:
            note = None

        return ControllerResponse.render(success=success, message=message, details=details, note=note)

    @staticmethod
    def input_result(
        field_name: str | None,
        value: str | None = None,
        success: bool = True,
        details: str | None = None,
    ) -> str:
        """Render an input action result response."""
        field = field_name or "<unnamed>"
        if value:
            message = f"Input '{value}' into '{field}'"
        else:
            message = f"Cleared input in '{field}'"

        return ControllerResponse.render(success=success, message=message, details=details)

    @staticmethod
    def swipe_result(
        direction: str,
        start: tuple | None = None,
        end: tuple | None = None,
        success: bool = True,
    ) -> str:
        """Render a swipe gesture result response."""
        message = f"Swiped {direction}"
        if start and end:
            details = f"From ({start[0]}, {start[1]}) to ({end[0]}, {end[1]})"
        else:
            details = None

        return ControllerResponse.render(success=success, message=message, details=details)

    @staticmethod
    def tap_result(
        x: int,
        y: int,
        element_name: str | None = None,
        success: bool = True,
        details: str | None = None,
    ) -> str:
        """Render a tap action result response."""
        if element_name:
            message = f"Tapped at ({x}, {y}) (resolved from '{element_name}')"
        else:
            message = f"Tapped at ({x}, {y})"

        return ControllerResponse.render(success=success, message=message, details=details)

    @staticmethod
    def screenshot_result(
        success: bool = True, filename: str | None = None, error: str | None = None
    ) -> str:
        """Render a screenshot capture result response."""
        if success:
            message = "Screenshot captured"
            note = f"Saved as: {filename}" if filename else None
            return ControllerResponse.success(message=message, note=note)
        else:
            message = "Failed to capture screenshot"
            return ControllerResponse.error(message=message, details=error)
