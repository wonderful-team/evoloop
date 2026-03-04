"""
Human Interaction Types for Backend-to-Frontend Communication

This module defines standardized interaction types that the backend can send
to the frontend to request human input or actions. All interactions are
blocking (agent paused) until user responds.
"""
from enum import Enum
from typing import Any, Literal


class HumanRequestType(str, Enum):
    """Types of human requests that backend can make."""

    # Traditional text input
    TEXT_INPUT = "text_input"
    """Request text input from user (traditional HITL)."""

    # Project-related
    PROJECT_SWITCH = "project_switch"
    """Request user to switch to a specific project or select from list."""

    # Confirmation
    CONFIRM = "confirm"
    """Request yes/no confirmation from user."""

    # File selection
    FILE_SELECT = "file_select"
    """Request user to select one or more files."""


def create_text_input_request(
    prompt: str,
    placeholder: str | None = None,
    multiline: bool = False,
    allow_cancel: bool = True
) -> dict[str, Any]:
    """
    Create a human request for text input.

    Args:
        prompt: Message shown to user
        placeholder: Input placeholder text
        multiline: Whether to allow multiline input
        allow_cancel: Whether user can cancel

    Returns:
        Human request data structure
    """
    return {
        "type": HumanRequestType.TEXT_INPUT,
        "prompt": prompt,
        "placeholder": placeholder or "Enter your response...",
        "multiline": multiline,
        "allow_cancel": allow_cancel,
    }


def create_project_switch_request(
    message: str = "This operation requires a specific project.",
    allow_global: bool = False,
    suggested_project_id: int | None = None,
    show_project_list: bool = True,
    allow_cancel: bool = True
) -> dict[str, Any]:
    """
    Create a human request for project switch.

    Args:
        message: Message to show user explaining why switch is needed
        allow_global: Whether to allow staying in global mode
        suggested_project_id: Specific project to suggest (optional)
        show_project_list: Whether to show the project selection list
        allow_cancel: Whether user can cancel

    Returns:
        Human request data structure
    """
    return {
        "type": HumanRequestType.PROJECT_SWITCH,
        "prompt": message,
        "allow_cancel": allow_cancel,
        "payload": {
            "allow_global": allow_global,
            "suggested_project_id": suggested_project_id,
            "show_project_list": show_project_list,
        }
    }


def create_confirm_request(
    prompt: str,
    title: str | None = None,
    confirm_text: str = "Confirm",
    cancel_text: str = "Cancel",
    allow_cancel: bool = True
) -> dict[str, Any]:
    """
    Create a human request for confirmation.

    Args:
        prompt: Message shown to user
        title: Dialog title
        confirm_text: Text for confirm button
        cancel_text: Text for cancel button
        allow_cancel: Whether user can cancel

    Returns:
        Human request data structure
    """
    return {
        "type": HumanRequestType.CONFIRM,
        "prompt": prompt,
        "title": title or "Confirmation Required",
        "allow_cancel": allow_cancel,
        "payload": {
            "confirm_text": confirm_text,
            "cancel_text": cancel_text,
        }
    }


def create_file_select_request(
    prompt: str,
    multiple: bool = False,
    file_types: list[str] | None = None,
    allow_cancel: bool = True
) -> dict[str, Any]:
    """
    Create a human request for file selection.

    Args:
        prompt: Message shown to user
        multiple: Whether to allow multiple file selection
        file_types: Allowed file extensions (e.g., [".py", ".js"])
        allow_cancel: Whether user can cancel

    Returns:
        Human request data structure
    """
    return {
        "type": HumanRequestType.FILE_SELECT,
        "prompt": prompt,
        "allow_cancel": allow_cancel,
        "payload": {
            "multiple": multiple,
            "file_types": file_types or [],
        }
    }


async def handle_global_mode_tool(
    tool_name: str,
    message: str | None = None
) -> str:
    """
    Handle global mode when a tool requires a specific project.
    This will PAUSE agent execution until user switches to a project or cancels.

    Args:
        tool_name: Name of the tool being called
        message: Custom message to show user

    Returns:
        Error message to return to LLM (if user cancels)

    Note:
        If user successfully switches project, the agent will resume and
        the tool will be called again automatically with the new project context.
    """
    from app.core.context.manager import ContextManager
    from app.core.monitoring.activity import activity_monitor

    ctx = ContextManager.current()
    default_msg = f"This operation requires a specific project. Please switch to a project to use {tool_name}."
    user_msg = message or default_msg

    if ctx.thread_id:
        # This will PAUSE the agent until user responds
        await activity_monitor.request_human_interaction(
            thread_id=ctx.thread_id,
            request_type=HumanRequestType.PROJECT_SWITCH,
            prompt=user_msg,
            payload={
                "allow_global": False,
                "show_project_list": True,
            },
            allow_cancel=True
        )
        # This line only reached if user cancels (otherwise agent resumes)
        return f"[Cancelled] {user_msg}"

    return user_msg
