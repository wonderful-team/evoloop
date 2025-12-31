from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from typing import Optional
import subprocess
import os


from app.logging import get_context

@tool
def list_files(path: str = ".", recursive: bool = False, config: RunnableConfig = None) -> str:
    """
    List files in a directory.
    By default is non-recursive. Set recursive=True for deep listing (careful with large projects).
    for structural understanding, prefer `get_annotated_tree`.
    """
    try:
        # Get working directory from context or config
        ctx = get_context()
        root = ctx.get("working_directory") or os.getcwd()
        if not ctx.get("working_directory") and config and "configurable" in config:
            root = config["configurable"].get("working_directory", root)

        # Use utils for resolution (optional, or stick to simple logic here since it's just 'ls')
        # But consistent resolution is better.
        # target_path = resolve_path(path, base_path=root)
        # However, list_files usually takes relative path.
        target_path = os.path.abspath(os.path.join(root, path))
        
        if not os.path.exists(target_path):
             return f"Error: Directory does not exist: {target_path}"

        from app.utils.process import run_command
        cmd = ["ls"]
        if recursive:
            cmd.append("-R")
        cmd.append(target_path)

        # run_command supports list args (safe)
        res = run_command(cmd)
        if not res.success:
            return f"Error: {res.stderr}"
        return res.stdout[:2000]  # Truncate long outputs
    except Exception as e:
        return f"Exception: {str(e)}"


@tool
def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None, config: RunnableConfig = None) -> str:
    """
    Read the contents of a file. Supports optional line range reading.
    Line numbers are 1-based.
    """
    try:
        from app.utils.file import resolve_path, read_file_content as utils_read_file
        
        ctx = get_context()
        root = ctx.get("working_directory") or os.getcwd()
        
        # Use new resolve_path logic
        target_path = resolve_path(path, base_path=root)
        
        if not target_path or not os.path.exists(target_path):
             return f"Error: File not found: {path} (Resolved: {target_path})"
             
        content, _ = utils_read_file(target_path, start_line, end_line)
        return content

    except Exception as e:
        return f"Error reading file: {str(e)}"


@tool
def edit_file(path: str, target: str, replacement: str, config: RunnableConfig = None) -> str:
    """
    Edit a file by replacing a specific target snippet with a replacement.
    Efficient for making changes without re-writing the whole document.
    
    Args:
        path: Relative path to the file.
        target: The exact text block to replace. Must be unique in the file.
        replacement: The new text block.
    """
    try:
        # Get working directory from context or config
        ctx = get_context()
        root = ctx.get("working_directory") or os.getcwd()
        if not ctx.get("working_directory") and config and "configurable" in config:
            root = config["configurable"].get("working_directory", root)
            
        target_path = os.path.abspath(os.path.join(root, path))
        
        if not os.path.exists(target_path):
            return f"Error: File not found: {target_path}"
            
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        count = content.count(target)
        
        if count == 0:
            return "Error: Target snippet not found. Check whitespace/indentation."
        elif count > 1:
            return f"Error: Target snippet found {count} times. Please include more context to make it unique."
            
        new_content = content.replace(target, replacement)
        
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        return f"Successfully edited {path}"
        
    except Exception as e:
        return f"Error editing file: {str(e)}"


@tool
def grep_files(pattern: str, path: str = ".", case_insensitive: bool = False, config: RunnableConfig = None) -> str:
    """
    Search for a text pattern in files using 'grep -r'.
    Useful for finding all usages of a function, class, or variable.
    """
    try:
        # Get working directory from context or config
        ctx = get_context()
        root = ctx.get("working_directory") or os.getcwd()
        if not ctx.get("working_directory") and config and "configurable" in config:
            root = config["configurable"].get("working_directory", root)
            
        target_path = os.path.abspath(os.path.join(root, path))

        # Construct command
        cmd = ["grep", "-r", "-n"]
        if case_insensitive:
            cmd.append("-i")

        # Exclude common junk
        cmd.extend([
            "--exclude-dir=.git",
            "--exclude-dir=__pycache__",
            "--exclude-dir=.venv",
            "--exclude-dir=node_modules"
        ])

        cmd.append(pattern)
        cmd.append(target_path)

        result = subprocess.run(cmd, capture_output=True, text=True)
        # Grep returns 1 if no matches found (which is not an error for us)
        if result.returncode > 1:
            return f"Error running grep: {result.stderr}"

        output = result.stdout
        if not output:
            return "No matches found."

        return output[:3000]  # Truncate
    except Exception as e:
        return f"Exception: {str(e)}"


@tool
def write_file_content(path: str, content: str, config: RunnableConfig = None) -> str:
    """
    Write content to a file.
    """
    try:
        from app.utils.file import resolve_path, write_file_contents as utils_write_file
        
        ctx = get_context()
        root = ctx.get("working_directory") or os.getcwd()
        
        # Standardize path logic, though write usually takes relative or absolute
        # creating a new file does not require existence check for 'resolve_path' usually 
        # but our new resolve_path returns absolute path if it thinks it should.
        # However, for writing to a NEW file, resolve_path might return None if it checks existence?
        # Let's see... implementation of resolve_path checks existence for relative paths to confirm match.
        # But returns full_path as logic for simple join if base_path is provided.
        # Wait, my resolve_path implementation:
        # if base_path: full_path = ...; if exists return full_path; else fuzzy search... return full_path (best guess).
        # So it returns full_path even if not exists. Good.

        target_path = resolve_path(path, base_path=root) or os.path.abspath(os.path.join(root, path))
        
        utils_write_file(content, target_path)
        return f"Successfully wrote to {target_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"
