import asyncio

from langchain_core.tools import tool

from app.logging import get_context
import logging

logger = logging.getLogger(__name__)


@tool
async def run_shell_command(command: str) -> str:
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
    
    ctx = get_context()
    cwd = ctx.get("working_directory")
    
    try:
        from app.utils.process import run_async_command
        
        # run_async_command handles timeouts and safe execution wrapper
        result = await run_async_command(command, cwd=cwd)
        
        output = ""
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"
            
        if result.success:
            return f"Command Succeeded.\n{output}"
        else:
            return f"Command Failed (Exit Code {result.returncode}).\n{output}"
            
    except Exception as e:
        return f"Execution Error: {str(e)}"

# Alias for consistent naming in prompts
run_command = run_shell_command
