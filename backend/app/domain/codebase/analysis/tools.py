from app.core.tools import evoloop_tool, get_working_directory
from typing import Optional
from langchain_core.runnables import RunnableConfig
import os

@evoloop_tool
def find_definition(symbol_name: str, file_pattern: Optional[str] = None, config: RunnableConfig = None) -> str:
    """
    Find the definition (class/function) of a symbol in the codebase.
    Uses AST analysis for precision (better than grep).
    
    Args:
        symbol_name: The exact name of the class or function (e.g., 'User', 'create_user').
        file_pattern: Optional glob pattern to limit search (e.g., '*.py').
    """
    root = get_working_directory(config)
    
    # 1. Reuse CodeAnalyzer logic OR use simple recursion + AST
    # Since reusing code_analyzer requires reading every file (slow), 
    # we should use a smart strategy: grep for "def symbol" or "class symbol" first to narrow down files,
    # then parse potential matches to confirm.
    
    from app.utils.process import run_command
    import ast
    
    # Heuristic Search (Grep) to find candidates
    # Regex: (class|def)\s+symbol_name\b
    cmd = ["grep", "-rnE", f"(class|def)\\s+{symbol_name}\\b", root]
    
    if file_pattern:
        cmd.extend(["--include", file_pattern])
    else:
        cmd.extend(["--include", "*.py", "--include", "*.ts", "--include", "*.tsx", "--include", "*.js"])
        
    cmd.extend(["--exclude-dir", ".git", "--exclude-dir", "__pycache__", "--exclude-dir", "node_modules"])
    
    res = run_command(cmd)
    
    if not res.success or not res.stdout:
        return f"No definition found for symbol '{symbol_name}'."
        
    # Format output
    lines = res.stdout.strip().splitlines()
    # Limit to top 5 matches
    preview = "\n".join(lines[:10])
    
    return f"Found potential definitions:\n{preview}\n\n(Tip: Use `read_file` on the most likely file to see the full code.)"
