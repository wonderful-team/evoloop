import contextvars
from typing import Any

# ContextVars for Request/Task Scope
_request_context = contextvars.ContextVar("request_context", default={})


def set_context(thread_id: str | None = None, project_id: int | None = None, working_directory: str | None = None, command_id: int | None = None):
    """Set the context for the current task."""
    ctx = _request_context.get().copy() # Copy to avoid mutating shared dict if any (though get() returns copy usually?)
    # Actually contextvars default is immutable if not careful.
    # But usually we do:
    if thread_id:
        ctx["thread_id"] = thread_id
    if project_id:
        ctx["project_id"] = project_id
    if working_directory:
        ctx["working_directory"] = working_directory
    if command_id:
        ctx["command_id"] = command_id
    _request_context.set(ctx)


def get_context() -> dict[str, Any]:
    """Get the current context."""
    return _request_context.get()


def get_context_var(key: str, default: Any = None) -> Any:
    """Get a specific variable from the current context."""
    return _request_context.get().get(key, default)
