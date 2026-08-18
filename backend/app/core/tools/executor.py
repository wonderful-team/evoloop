import logging
from typing import Any

from app.core.tools.base import EvoLoopTool as BaseTool

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Service to execute tools with error handling and boundary learning."""

    async def execute(self, tool: BaseTool, args: dict[str, Any] | str, config: dict | None = None) -> Any:
        tool_name = tool.name
        try:
            # MCP 写工具确认门控：description 标注 [confirm:true] 的高风险写工具
            # 必须经运营人员确认后才执行（业务性文案，不暴露工具名）。
            from app.core.hitl.mcp_confirmation import maybe_gate_mcp_tool

            if isinstance(args, dict):
                await maybe_gate_mcp_tool(tool_name, tool.description or "", args, config)
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
                logger.debug(f"Boundary learning failed: {boundary_err}", exc_info=True)
            return f"Error executing {tool_name}: {str(e)}"
