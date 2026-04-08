"""
Human Interaction Types for Backend-to-Frontend Communication

This module defines standardized interaction types that the backend can send
to the frontend to request human input or actions. All interactions are
blocking (agent paused) until user responds.
"""
from enum import Enum
from typing import Any


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

    # Approval
    APPROVAL = "approval"
    """Request explicit approval for impactful actions."""

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
    temporary: bool = True,
    allow_cancel: bool = True
) -> dict[str, Any]:
    """
    Create a human request for project switch.

    Args:
        message: Message to show user explaining why switch is needed
        allow_global: Whether to allow staying in global mode
        suggested_project_id: Specific project to suggest (optional)
        show_project_list: Whether to show the project selection list
        temporary: Whether this is a temporary project switch (Scheme C)
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
            "temporary": temporary,
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


# =============================================================================
# Global Mode Helpers - For tools that need a project in global mode
# =============================================================================

GLOBAL_MODE_MESSAGES = {
    "code_search": "[Global Mode]: Code search requires a project. Please provide a project_id or switch to a project.",
    "wiki": "[Global Mode]: Wiki requires a project.",
    "architecture": "[Global Mode]: Architecture consultation requires a project.",
    "file_operation": "[Global Mode]: File operations require a project.",
    "git": "[Global Mode]: Git operations require a project.",
    "default": "[Global Mode]: This operation requires a specific project.",
}


def get_global_mode_message(tool_category: str = "default") -> str:
    """Return standardized error message for global mode restriction."""
    return GLOBAL_MODE_MESSAGES.get(tool_category, GLOBAL_MODE_MESSAGES["default"])


async def resolve_project_with_hitl(
    tool_name: str,
    prompt: str | None = None,
    tool_category: str = "default",
    temporary: bool = True
) -> int | None:
    """
    Resolve project ID in global mode, requesting user selection if needed.

    This helper handles the complete flow:
    1. Check if temp project is already set (Scheme C)
    2. If not, request human interaction to select a project
    3. Returns project_id if available, None if user cancelled

    Args:
        tool_name: Name of the tool for logging
        prompt: Custom prompt message (optional)
        tool_category: Category for default message (code_search/wiki/architecture/etc.)
        temporary: Whether this is a temporary project switch (Scheme C)

    Returns:
        Project ID if resolved, None if user cancelled or error
    """
    from app.core.context.manager import ContextManager
    from app.core.context.thread_store import thread_context_store
    from app.core.monitoring.activity import activity_monitor

    ctx = ContextManager.current()
    if not ctx.thread_id:
        return None

    # Check for temporary project (Scheme C)
    temp_project = thread_context_store.get_temp_project(ctx.thread_id)
    if temp_project is not None:
        # Clear temp project after use (one-time)
        thread_context_store.set_temp_project(ctx.thread_id, None)
        return temp_project

    # No temp project - request human interaction
    user_prompt = prompt or get_global_mode_message(tool_category)

    await activity_monitor.request_human_interaction(
        thread_id=ctx.thread_id,
        request_type=HumanRequestType.PROJECT_SWITCH,
        prompt=user_prompt,
        payload={
            "allow_global": False,
            "show_project_list": True,
            "temporary": temporary,
        },
        allow_cancel=True
    )

    # This line is only reached if user cancels
    return None


async def require_project_for_tool(
    tool_name: str,
    tool_category: str = "default",
    prompt: str | None = None
) -> int | str:
    """
    Require a project for tool execution in global mode.

    This is a higher-level wrapper that returns either:
    - int: The resolved project_id (continue tool execution)
    - str: Error message to return to LLM (user cancelled)

    Args:
        tool_name: Name of the tool being called
        tool_category: Category for default message
        prompt: Custom prompt message (optional)

    Returns:
        Project ID (int) if successful, error message (str) if cancelled
    """
    project_id = await resolve_project_with_hitl(
        tool_name=tool_name,
        prompt=prompt,
        tool_category=tool_category,
        temporary=True  # Always use Scheme C (temporary) for tool calls
    )

    if project_id is None:
        return get_global_mode_message(tool_category)

    return project_id


async def handle_global_mode_tool(
    tool_name: str,
    message: str | None = None
) -> str:
    """
    Handle global mode when a tool requires a specific project.
    This will PAUSE agent execution until user switches to a project or cancels.

    DEPRECATED: Use `require_project_for_tool()` or `resolve_project_with_hitl()` instead
    for better integration with tool logic.

    Args:
        tool_name: Name of the tool being called
        message: Custom message to show user

    Returns:
        Error message to return to LLM (if user cancels)
    """
    ctx_result = await require_project_for_tool(tool_name, "default", message)

    # If int is returned, it means project was resolved (shouldn't happen in this flow)
    if isinstance(ctx_result, int):
        return f"[Project Resolved] {ctx_result}"

    return ctx_result
