import logging
from typing import Any

from app.core.tools.base import EvoLoopTool as BaseTool

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Service to execute tools with error handling and boundary learning.

    本类保持哑执行器职责：不感知 HITL/门控等上层策略，仅执行工具。
    """

    async def execute(
        self, tool: BaseTool, args: dict[str, Any] | str, config: dict | None = None
    ) -> Any:
        tool_name = tool.name
        try:
            return await tool.ainvoke(args, config=config)
        except InterruptedError:
            raise
        except Exception as e:
            try:
                from app.core.environment.boundaries import boundary_manager

                await boundary_manager.on_tool_failure(
                    tool_name, e, context={"args": str(args)[:200]}
                )
            except Exception as boundary_err:
                logger.debug(f"Boundary learning failed: {boundary_err}", exc_info=True)
            return f"Error executing {tool_name}: {str(e)}"
