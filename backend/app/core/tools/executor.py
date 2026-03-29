import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from app.core.evocloud.callback_handler import EvoCloudCallbackHandler
from app.core.tools.cache import tool_cache

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    Service to execute tools with enhanced observability.
    Ensures that start/end events are logged to the frontend via EvoCloudCallbackHandler.
    """

    def __init__(self):
        pass

    async def execute(self, tool: BaseTool, args: dict[str, Any] | str, config: RunnableConfig) -> Any:
        """
        Execute a tool with optional caching and ensure distinct 'tool_start' and 'tool_end' feedback.

        Args:
            tool: The LangChain tool instance.
            args: Arguments for the tool.
            config: RunnableConfig, must contain 'callbacks' to work effectively with standard LC mechanisms.
        """
        callbacks = config.get("callbacks", []) if config else []
        evoloop_handler: EvoCloudCallbackHandler | None = None

        # Normalize callbacks to a list
        callback_list = []
        if isinstance(callbacks, list):
            callback_list = callbacks
        elif hasattr(callbacks, "handlers"):
            callback_list = callbacks.handlers

        # Find EvoCloud handler
        for cb in callback_list:
            if isinstance(cb, EvoCloudCallbackHandler):
                evoloop_handler = cb
                break

        tool_name = tool.name
        input_str = json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(args)

        # 1. Log Start
        if evoloop_handler:
            try:
                await evoloop_handler.on_tool_start(
                    serialized={"name": tool_name},
                    input_str=input_str
                )
            except Exception as e:
                logger.error(f"Failed to log tool start: {e}")

        # 2. Execute with caching
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

        # 3. Log End (include cache status)
        if evoloop_handler:
            try:
                cache_indicator = " [CACHED]" if cache_meta.get('cached') else ""
                await evoloop_handler.on_tool_end(
                    output=str(output) + cache_indicator
                )
            except Exception as e:
                logger.error(f"Failed to log tool end: {e}")

        # Log cache hit for monitoring
        if cache_meta.get('cached'):
            logger.info(f"[ToolExecutor] 🎯 Cache hit: {tool_name} "
                       f"(age: {cache_meta.get('age_seconds', 0):.1f}s, "
                       f"accesses: {cache_meta.get('access_count', 1)})")

        return output
