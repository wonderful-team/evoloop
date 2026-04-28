import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from app.core.tools.cache import tool_cache

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    Service to execute tools with optional caching.
    Tool start/end events are handled by DatabaseCallbackHandler via LangChain callbacks.
    """

    def __init__(self):
        pass

    async def execute(self, tool: BaseTool, args: dict[str, Any] | str, config: RunnableConfig) -> Any:
        """
        Execute a tool with optional caching.

        Args:
            tool: The LangChain tool instance.
            args: Arguments for the tool.
            config: RunnableConfig.
        """
        tool_name = tool.name

        # Execute with caching
        async def _do_execute():
            try:
                return await tool.ainvoke(args, config=config)
            except InterruptedError:
                raise
            except Exception as e:
                # Learn from failure
                try:
                    from app.core.environment.boundaries import boundary_manager
                    await boundary_manager.on_tool_failure(tool_name, e, context={
                        "args": str(args)[:200]
                    })
                except Exception as boundary_err:
                    logger.debug(f"Boundary learning failed: {boundary_err}")
                return f"Error executing {tool_name}: {str(e)}"

        # Normalize args to dict for caching
        args_dict = args if isinstance(args, dict) else {"_arg": args}

        # Execute with cache
        output, cache_meta = await tool_cache.execute(
            tool_name=tool_name,
            args=args_dict,
            execute_fn=_do_execute,
            config=config
        )

        # Log cache hit for monitoring
        if cache_meta.get('cached'):
            logger.info(f"[ToolExecutor] 🎯 Cache hit: {tool_name} "
                       f"(age: {cache_meta.get('age_seconds', 0):.1f}s, "
                       f"accesses: {cache_meta.get('access_count', 1)})")

        return output
