"""Core command execution — synchronous and tool-level interfaces."""

import asyncio
import logging
from typing import Annotated

from app.core.context import ContextManager
from app.core.engine.message.native_classes import RunnableConfig
from app.core.tools import evoloop_tool, get_working_directory
from app.core.tools.base import InjectedToolArg
from app.infrastructure.config import SystemConfigService
from app.domain.tools.execution.background import execute_in_background, execute_smart
from app.domain.tools.execution.security import is_dangerous_command

logger = logging.getLogger(__name__)


async def _execute_command(
    command: str, config: RunnableConfig | None = None
) -> tuple[str, str, int]:
    logger.info(f"Execution [Command]: {command}")

    is_dangerous, reason = is_dangerous_command(command)
    if is_dangerous:
        logger.warning(f"Blocked dangerous command: {command}")
        return "", f"Security Error: {reason}", 1

    try:
        from app.core.execution import SandboxFactory

        ctx = ContextManager.current()
        working_dir = get_working_directory(config)

        if ctx.project_id == 0 or (ctx.project_id is None and working_dir == "."):
            workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
            if workspace_root:
                working_dir = workspace_root
                logger.info(f"Global mode: Using WORKSPACE_ROOT as working directory: {working_dir}")

        sandbox = SandboxFactory.get_sandbox()

        if working_dir and working_dir != ".":
            wrapped_command = f"cd {working_dir} && {command}"
        else:
            wrapped_command = command

        stdout, stderr, returncode = await asyncio.to_thread(sandbox.run_command, wrapped_command)

        return stdout, stderr, returncode

    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"Command execution error: {e}")
        return "", str(e), -1


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
