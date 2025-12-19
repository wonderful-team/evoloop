from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from typing import Optional
import subprocess
import os


@tool
def list_files(path: str = ".", config: RunnableConfig = None) -> str:
    """
    List files in a directory using 'ls -R'.
    Useful for understanding directory structure.
    """
    try:
        # Get working directory from config
        root = os.getcwd()
        if config and "configurable" in config:
            root = config["configurable"].get("working_directory", root)

        # Resolve path relative to root
        target_path = os.path.abspath(os.path.join(root, path))
        
        # Security check: Ensure we are within allowed bounds (omitted for dev agent flexibility)
        
        # Security: In production, sanitize input strictly.
        # Here we assume local trusted dev environment.
        # We assume 'ls' is available.
        if not os.path.exists(target_path):
             return f"Error: Directory does not exist: {target_path}"

        result = subprocess.run(["ls", "-R", target_path], capture_output=True, text=True)
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        return result.stdout[:2000]  # Truncate long outputs
    except Exception as e:
        return f"Exception: {str(e)}"


@tool
def read_file(path: str, config: RunnableConfig = None) -> str:
    """
    Read the contents of a file.
    """
    try:
        # Get working directory from config
        root = os.getcwd()
        if config and "configurable" in config:
            root = config["configurable"].get("working_directory", root)
            
        # Resolve full path
        target_path = os.path.abspath(os.path.join(root, path))
        
        if not os.path.exists(target_path):
            return f"Error: File not found: {target_path}"

        with open(target_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"


@tool
def grep_files(pattern: str, path: str = ".", case_insensitive: bool = False, config: RunnableConfig = None) -> str:
    """
    Search for a text pattern in files using 'grep -r'.
    Useful for finding all usages of a function, class, or variable.
    """
    try:
        # Get working directory from config
        root = os.getcwd()
        if config and "configurable" in config:
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
        # Get working directory from config
        root = os.getcwd()
        if config and "configurable" in config:
            root = config["configurable"].get("working_directory", root)

        target_path = os.path.abspath(os.path.join(root, path))
        
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {target_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"
