import functools
import logging
import os

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool as langchain_tool

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

    # Default
    return os.getcwd()


def evoloop_tool(func):
    """
    Decorator that applies standard EvoLoop tool behaviors:
    1. Wraps execution in a try/except block to return formatted error strings.
    2. (Implicitly) relies on `get_working_directory` being used inside.

    Usage:
    @evoloop_tool
    def my_tool(args, config: RunnableConfig): ...
    """
    import inspect

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Debug: Log raw inputs
            logger.info(f"🔧 Tool [{func.__name__}] Invoked - Args: {args}, Kwargs: {kwargs}")
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Log error
                return f"Error: {str(e)}"
    else:

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Debug: Log raw inputs
            logger.info(f"🔧 Tool [{func.__name__}] Invoked - Args: {args}, Kwargs: {kwargs}")
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Log error
                return f"Error: {str(e)}"

    # Mark for Auto-Discovery on the wrapper function
    wrapper.is_evoloop_active = True
    wrapper.evoloop_module = func.__module__

    # Apply LangChain's @tool
    tool_instance = langchain_tool(wrapper)

    # Enable error handling to return validation errors as text to the Agent
    tool_instance.handle_tool_error = True

    return tool_instance
