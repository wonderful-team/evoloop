import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Service to execute tools with error handling and boundary learning."""

    async def execute(self, tool: BaseTool, args: dict[str, Any] | str, config: RunnableConfig) -> Any:
        tool_name = tool.name
        try:
            return await tool.ainvoke(args, config=config)
        except InterruptedError:
            raise
        except Exception as e:
            try:
                from app.core.environment.boundaries import boundary_manager
                await boundary_manager.on_tool_failure(tool_name, e, context={
                    "args": str(args)[:200]
                })
            except Exception as boundary_err:
                logger.debug(f"Boundary learning failed: {boundary_err}")
            return f"Error executing {tool_name}: {str(e)}"
