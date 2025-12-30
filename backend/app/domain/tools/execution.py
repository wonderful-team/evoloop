import asyncio

from langchain_core.tools import tool

from app.logging import get_context


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
    print(f"Tester [Running]: {command}")
    
    # Security Warning: This is a high-risk tool. 
    # In production, this should be sandboxed (Docker/gVisor).
    # For this local assistant, we assume trust.
    
    ctx = get_context()
    cwd = ctx.get("working_directory")
    
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        stdout, stderr = await process.communicate()
        
        output = ""
        if stdout:
            output += f"STDOUT:\n{stdout.decode().strip()}\n"
        if stderr:
            output += f"STDERR:\n{stderr.decode().strip()}\n"
            
        if process.returncode == 0:
            return f"Command Succeeded.\n{output}"
        else:
            return f"Command Failed (Exit Code {process.returncode}).\n{output}"
            
    except Exception as e:
        return f"Execution Error: {str(e)}"
