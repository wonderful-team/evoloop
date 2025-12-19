import subprocess
from langchain_core.tools import tool
import asyncio


@tool
async def run_shell_command(command: str) -> str:
    """
    Run a shell command (e.g., 'pytest', 'ls', 'cat').
    Useful for running tests, checking syntax, or verifying file creation.
    """
    print(f"Tester [Running]: {command}")
    
    # Security Warning: This is a high-risk tool. 
    # In production, this should be sandboxed (Docker/gVisor).
    # For this local assistant, we assume trust.
    
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
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
