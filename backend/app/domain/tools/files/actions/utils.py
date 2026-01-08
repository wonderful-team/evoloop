from typing import Optional
import os
from langchain_core.runnables import RunnableConfig
from app.core.tools import get_working_directory
from app.utils.file import resolve_path

def resolve_and_validate_path(path: str, config: Optional[RunnableConfig] = None) -> str:
    """
    Resolve path and perform security check.
    Raises ValueError on security violation or resolution failure.
    """
    # Handle Agent Hallucinations (treating system root dependencies)
    if path.strip() == "/" or path.strip() == "":
        path = "."
        
    root = get_working_directory(config)
    target_path = resolve_path(path, base_path=root)
    
    if not target_path: # Could not resolve
         raise ValueError(f"Error: Could not resolve path: {path}")
         
    # Security Check: Prevent breaking out of working directory
    if not str(target_path).startswith(str(root)):
        raise ValueError(f"Error: Security Violation. Path '{path}' is outside the working directory '{root}'. Please use relative paths.")
        
    return target_path
