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
    For structural understanding, prefer `get_annotated_tree`.
    """
    try:
        # Get working directory from context or config
        ctx = get_context()
        root = ctx.get("working_directory") or os.getcwd()
        if not ctx.get("working_directory") and config and "configurable" in config:
            root = config["configurable"].get("working_directory", root)

        # Resolve path relative to root
        target_path = os.path.abspath(os.path.join(root, path))
        
        if not os.path.exists(target_path):
             return f"Error: Directory does not exist: {target_path}"

        cmd = ["ls"]
        if recursive:
            cmd.append("-R")
        cmd.append(target_path)

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        return result.stdout[:2000]  # Truncate long outputs
    except Exception as e:
        return f"Exception: {str(e)}"


@tool
def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None, config: RunnableConfig = None) -> str:
    """
    Read the contents of a file. Supports optional line range reading.
    Line numbers are 1-based.
    """
    try:
        # Get working directory from context or config
        ctx = get_context()
        root = ctx.get("working_directory") or os.getcwd()
        if not ctx.get("working_directory") and config and "configurable" in config:
            root = config["configurable"].get("working_directory", root)
            
        # Resolve full path
        target_path = os.path.abspath(os.path.join(root, path))
        
        if not os.path.exists(target_path):
            return f"Error: File not found: {target_path}"

        with open(target_path, "r", encoding="utf-8") as f:
            if start_line is None and end_line is None:
                return f.read()
            
            lines = f.readlines()
            total_lines = len(lines)
            
            start = max(0, start_line - 1) if start_line else 0
            end = min(total_lines, end_line) if end_line else total_lines
            
            if start >= total_lines:
                return ""
            
            # Return raw content of chunks
            return "".join(lines[start:end])

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
        # Get working directory from context or config
        ctx = get_context()
        root = ctx.get("working_directory") or os.getcwd()
        if not ctx.get("working_directory") and config and "configurable" in config:
            root = config["configurable"].get("working_directory", root)

        target_path = os.path.abspath(os.path.join(root, path))
        
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {target_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"
