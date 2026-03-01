import asyncio
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.constants import DEFAULT_EXCLUDED_DIRS
from app.core.tools import evoloop_tool
from app.utils.process import run_command

from .actions.utils import resolve_and_validate_path


@evoloop_tool(is_pollable=True)
async def grep_files(
    pattern: str,
    path: str = ".",
    case_insensitive: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Search for a text pattern in files using 'grep -r'.
    Useful for finding all usages of a function, class, or variable.
    """
    try:
        target_path = resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    cmd = ["grep", "-r", "-n"]
    if case_insensitive:
        cmd.append("-i")

    # Use standard excluded directories
    for excluded_dir in DEFAULT_EXCLUDED_DIRS:
        cmd.append(f"--exclude-dir={excluded_dir}")

    cmd.append(pattern)
    cmd.append(target_path)

    res = await asyncio.to_thread(run_command, cmd)
    if not res.success:
        # grep returns 1 if no lines found
        if res.returncode == 1:
            return "No matches found."
        return f"Error running grep: {res.stderr}"

    return res.stdout[:3000]
