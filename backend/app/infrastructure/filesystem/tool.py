import os
import subprocess
from langchain_core.runnables import RunnableConfig
from typing import Optional

from app.core.tools import evoloop_tool, get_working_directory
from app.utils.process import run_command
from app.utils.file import resolve_path, read_file_content as utils_read_file, write_file_contents as utils_write_file

@evoloop_tool
def list_files(path: str = ".", recursive: bool = False, config: RunnableConfig = None) -> str:
    """
    List files in a directory.
    By default is non-recursive. Set recursive=True for deep listing (careful with large projects).
    for structural understanding, prefer `manage_file(action='list_tree')`.
    """
    root = get_working_directory(config)
    target_path = os.path.abspath(os.path.join(root, path))
    
    if not os.path.exists(target_path):
         return f"Error: Directory does not exist: {target_path}"

    cmd = ["ls"]
    if recursive:
        cmd.append("-R")
    cmd.append(target_path)

    res = run_command(cmd)
    if not res.success:
        return f"Error: {res.stderr}"
    return res.stdout[:2000]

@evoloop_tool
def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None, config: RunnableConfig = None) -> str:
    """
    Read the contents of a file. Supports optional line range reading.
    Line numbers are 1-based.
    """
    root = get_working_directory(config)
    target_path = resolve_path(path, base_path=root)
    
    if not target_path or not os.path.exists(target_path):
         return f"Error: File not found: {path} (Resolved: {target_path})"
         
    content, _ = utils_read_file(target_path, start_line, end_line)
    return content

@evoloop_tool
def edit_file(path: str, target: str, replacement: str, config: RunnableConfig = None) -> str:
    """
    Edit a file by replacing a specific target snippet with a replacement.
    Efficient for making changes without re-writing the whole document.
    
    Args:
        path: Relative path to the file.
        target: The exact text block to replace. Must be unique in the file.
        replacement: The new text block.
    """
    root = get_working_directory(config)
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

@evoloop_tool
def grep_files(pattern: str, path: str = ".", case_insensitive: bool = False, config: RunnableConfig = None) -> str:
    """
    Search for a text pattern in files using 'grep -r'.
    Useful for finding all usages of a function, class, or variable.
    """
    root = get_working_directory(config)
    target_path = os.path.abspath(os.path.join(root, path))

    cmd = ["grep", "-r", "-n"]
    if case_insensitive:
        cmd.append("-i")

    cmd.extend([
        "--exclude-dir=.git",
        "--exclude-dir=__pycache__",
        "--exclude-dir=.venv",
        "--exclude-dir=node_modules"
    ])

    cmd.append(pattern)
    cmd.append(target_path)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode > 1:
        return f"Error running grep: {result.stderr}"

    output = result.stdout
    if not output:
        return "No matches found."

    return output[:3000]

@evoloop_tool
def write_file_content(path: str, content: str, config: RunnableConfig = None) -> str:
    """
    Write content to a file.
    """
    root = get_working_directory(config)
    # Use resolve_path but fall back to join if simply creating new file
    target_path = resolve_path(path, base_path=root) or os.path.abspath(os.path.join(root, path))
    
    utils_write_file(content, target_path)
    return f"Successfully wrote to {target_path}"
