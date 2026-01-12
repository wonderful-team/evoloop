import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from app.core.callbacks.evoloop_logger import EvoLoopCallbackHandler

logger = logging.getLogger(__name__)

class ToolExecutor:
    """
    Service to execute tools with enhanced observability.
    Ensures that start/end events are logged to the frontend via EvoLoopCallbackHandler.
    """

    def __init__(self):
        pass

    async def execute(
        self,
        tool: BaseTool,
        args: dict[str, Any] | str,
        config: RunnableConfig
    ) -> Any:
        """
        Execute a tool and ensure distinct 'tool_start' and 'tool_end' feedback is sent.
        
        Args:
            tool: The LangChain tool instance.
            args: Arguments for the tool.
            config: RunnableConfig, must contain 'callbacks' to work effectively with standard LC mechanisms.
                    However, we also manually trigger specific logs if the handler is found.
        """
        callbacks = config.get("callbacks", []) if config else []
        evoloop_handler: EvoLoopCallbackHandler | None = None

        # Normalize callbacks to a list
        callback_list = []
        if isinstance(callbacks, list):
            callback_list = callbacks
        elif hasattr(callbacks, "handlers"):
            # Handle AsyncCallbackManager/CallbackManager
            callback_list = callbacks.handlers

        # Find EvoLoop handler to force-feed logs if needed
        for cb in callback_list:
            if isinstance(cb, EvoLoopCallbackHandler):
                evoloop_handler = cb
                break

        tool_name = tool.name

        # Helper to format input string
        input_str = json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(args)

        # 1. Log Start (Manual enforcement to guarantee UI update)
        if evoloop_handler:
            try:
                await evoloop_handler.on_tool_start(
                    serialized={"name": tool_name},
                    input_str=input_str
                )
            except Exception as e:
                logger.error(f"Failed to log tool start: {e}")

        # 2. Execute
        try:
            # We assume the tool itself handles exceptions via @evoloop_tool,
            # but we allow bubbling if raw execution
            output = await tool.ainvoke(args, config=config)
        except InterruptedError:
            raise
        except Exception as e:
            output = f"Error executing {tool_name}: {str(e)}"

        # 3. Log End
        if evoloop_handler:
            try:
                await evoloop_handler.on_tool_end(
                    output=str(output)
                )
            except Exception as e:
                logger.error(f"Failed to log tool end: {e}")

        return output
