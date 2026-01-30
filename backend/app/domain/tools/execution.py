import asyncio
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def run_command(command: str) -> str:
    """
    Run a shell command (e.g., 'pytest', 'npm install').

    WARNING: Use dedicated tools for standard operations:
    - Version Control -> Use `git_*` tools.
    - File Editing -> Use `edit_file` / `write_file_content`.
    - File Reading -> Use `read_file`.

    Only use this for execution tasks like running tests, builds, or scripts.
    """
    logger.info(f"Tester [Running]: {command}")

    # Security Warning: This is a high-risk tool.
    # In production, this should be sandboxed (Docker/gVisor).
    # For this local assistant, we assume trust.

    try:
        from app.core.execution import SandboxFactory

        sandbox = SandboxFactory.get_sandbox()

        # Run via Sandbox
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
