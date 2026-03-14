import functools
import logging
import os

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool as langchain_tool

from app.core.config import settings
from app.core.context.manager import ContextManager

logger = logging.getLogger(__name__)


def get_working_directory(config: RunnableConfig | None = None) -> str:
    """
    Extracts the working directory from the context or configuration.
    Prioritizes:
    1. Context variable 'working_directory'
    2. Config 'measurable' > 'working_directory' (Legacy)
    3. os.getcwd()
    """
    # 1. Check ContextVar
    ctx = ContextManager.current()
    if ctx.working_directory:
        return ctx.working_directory

    # 2. Check RunnableConfig
    if config and "configurable" in config:
        wd = config["configurable"].get("working_directory")
        if wd:
            return wd

    # 3. Fallback to SystemConfig WORKSPACE_ROOT
    try:
        from app.infrastructure.config.service import SystemConfigService
        db_workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
        workspace_root = db_workspace_root if db_workspace_root else settings.WORKSPACE_ROOT
        if workspace_root:
            return workspace_root
    except Exception as e:
        logger.warning(f"Failed to fetch WORKSPACE_ROOT for tool fallback: {e}")

    # 4. Final Fallback
    return os.getcwd()


def evoloop_tool(
    *args,
    is_pollable: bool = False,
    is_state_mutating: bool = False,
    affected_path_keys: list[str] | None = None,
    summary_template: str | None = None,
    result_summary_template: str | None = None,
    **kwargs,
):
    """
    Decorator that applies standard EvoLoop tool behaviors.
    Can be used as @evoloop_tool or @evoloop_tool(name="...", is_pollable=True, ...).
    """
    import inspect

    def decorator(func):
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def wrapper(*args_f, **kwargs_f):
                # Debug: Log raw inputs
                logger.info(f"🔧 Tool [{func.__name__}] Invoked - Args: {args_f}, Kwargs: {kwargs_f}")
                try:
                    return await func(*args_f, **kwargs_f)
                except Exception as e:
                    # Log error
                    return f"Error: {str(e)}"
        else:

            @functools.wraps(func)
            def wrapper(*args_f, **kwargs_f):
                # Debug: Log raw inputs
                logger.info(f"🔧 Tool [{func.__name__}] Invoked - Args: {args_f}, Kwargs: {kwargs_f}")
                try:
                    return func(*args_f, **kwargs_f)
                except Exception as e:
                    # Log error
                    return f"Error: {str(e)}"

        # Mark for Auto-Discovery on the wrapper function
        wrapper.is_evoloop_active = True
        wrapper.evoloop_module = func.__module__

        # Apply LangChain's @tool (passing through any arguments)
        tool_instance = langchain_tool(*args, **kwargs)(wrapper)

        # Inject EvoLoop metadata for engine orchestration
        if not hasattr(tool_instance, "metadata") or tool_instance.metadata is None:
            tool_instance.metadata = {}
        tool_instance.metadata["is_pollable"] = is_pollable
        tool_instance.metadata["is_state_mutating"] = is_state_mutating
        tool_instance.metadata["affected_path_keys"] = affected_path_keys or []
        tool_instance.metadata["summary_template"] = summary_template
        tool_instance.metadata["result_summary_template"] = result_summary_template

        # Enable error handling to return validation errors as text to the Agent
        tool_instance.handle_tool_error = True

        return tool_instance

    # Handle both @evoloop_tool and @evoloop_tool(...)
    if len(args) == 1 and callable(args[0]):
        # Used as @evoloop_tool
        func = args[0]
        args = ()
        return decorator(func)
    else:
        # Used as @evoloop_tool(...)
        return decorator
