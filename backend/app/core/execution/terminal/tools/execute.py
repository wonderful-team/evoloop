"""Core command execution — synchronous and tool-level interfaces."""

import logging
from typing import Annotated

from app.core.engine.message.native_classes import RunnableConfig
from app.core.execution.terminal.background.runner import (
    execute_in_background,
    execute_smart,
)
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.execute_command",
)
async def execute_command(
    command: str,
    background: bool = False,
    timeout: int = 60,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    timeout = min(max(timeout, 10), 3600)

    if background:
        return await execute_in_background(command, timeout, config)
    else:
        return await execute_smart(command, timeout, config)
