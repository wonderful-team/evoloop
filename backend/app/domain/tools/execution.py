import asyncio
import logging

from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool
async def bash(command: str) -> str:
    """
    Run a shell command (e.g., 'pytest', 'npm install', 'ls -la').

    This is your primary tool for navigating the OS, running scripts, building projects,
    and executing standard operating procedures.

    WARNING: Use dedicated tools for standard operations when available:
    - Version Control -> Use `manage_git` tools.
    - File Editing -> Use `edit_file` / `write_file`.
    - File Reading -> Use `read_file`.

    Only use this for execution tasks like running tests, builds, or scripts.
    """
    logger.info(f"Execution [Bash]: {command}")

    try:
        from app.core.execution import SandboxFactory

        sandbox = SandboxFactory.get_sandbox()

        # Run via Sandbox (handles stateful CWD/ENV if using LocalSandbox)
        stdout, stderr, returncode = await asyncio.to_thread(sandbox.run_command, command)

        output = ""
        if stdout:
            output += f"STDOUT:\n{stdout}\n"
        if stderr:
            output += f"STDERR:\n{stderr}\n"

        if returncode == 0:
            return f"Command Succeeded.\n{output}"
        else:
            return f"Command Failed (Exit Code {returncode}).\n{output}"

    except Exception as e:
        return f"Execution Error: {str(e)}"
