"""
Human Interaction Types for Backend-to-Frontend Communication

This module defines standardized interaction types that the backend can send
to the frontend to request human input or actions. All interactions are
blocking (agent paused) until user responds.
"""

from app.core.monitoring import constants as monitoring_constants
from app.core.monitoring.schemas import HumanRequestData, HumanRequestType

# =============================================================================
# Workspace Mode Helpers - For tools that need a project in workspace mode
# =============================================================================


def get_global_mode_message(tool_category: str = "default") -> str:
    """Return standardized error message for global mode restriction."""
    return monitoring_constants.GLOBAL_MODE_MESSAGES.get(
        tool_category, monitoring_constants.GLOBAL_MODE_MESSAGES["default"]
    )


async def resolve_project_with_hitl(
    prompt: str | None = None,
    tool_category: str = "default",
    temporary: bool = True,
) -> int | None:
    """
    Resolve project ID in global mode, requesting user selection if needed.

    This helper handles the complete flow:
    1. Check if temp project is already set (Scheme C)
    2. If not, request human interaction to select a project
    3. Returns project_id if available, None if user cancelled

    Args:
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

    await activity_monitor.set_human_request(
        thread_id=ctx.thread_id,
        request_data=HumanRequestData(
            type=HumanRequestType.PROJECT_SWITCH,
            prompt=user_prompt,
            payload={
                "allow_global": False,
                "show_project_list": True,
                "temporary": temporary,
            },
            allow_cancel=True,
        ),
    )

    # This line is only reached if user cancels
    return None


async def require_project_for_tool(
    tool_category: str = "default", prompt: str | None = None
) -> int | str:
    """
    Require a project for tool execution in global mode.

    This is a higher-level wrapper that returns either:
    - int: The resolved project_id (continue tool execution)
    - str: Error message to return to LLM (user cancelled)

    Args:
        tool_category: Category for default message
        prompt: Custom prompt message (optional)

    Returns:
        Project ID (int) if successful, error message (str) if cancelled
    """
    project_id = await resolve_project_with_hitl(
        prompt=prompt,
        tool_category=tool_category,
        temporary=True,  # Always use Scheme C (temporary) for tool calls
    )

    if project_id is None:
        return get_global_mode_message(tool_category)

    return project_id
