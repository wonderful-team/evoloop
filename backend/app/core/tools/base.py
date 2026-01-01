import os
import functools
from typing import Optional, Any, Dict, Union
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool as langchain_tool
from app.logging import get_context

def get_working_directory(config: Optional[RunnableConfig] = None) -> str:
    """
    Extracts the working directory from the context or configuration.
    Prioritizes:
    1. Context variable 'working_directory'
    2. Config 'measurable' > 'working_directory'
    3. utils.file logic (if needed)
    4. os.getcwd()
    """
    # 1. Check ContextVar
    ctx = get_context()
    if ctx.get("working_directory"):
        return ctx["working_directory"]

    # 2. Check RunnableConfig
    if config and "configurable" in config:
        wd = config["configurable"].get("working_directory")
        if wd:
            return wd
            
    # Default
    return os.getcwd()

def evoloop_tool(func):
    """
    Decorator that applies standard EvoLoop tool behaviors:
    1. Wraps execution in a try/except block to return formatted error strings.
    2. (Implicitly) relies on `get_working_directory` being used inside.
    
    Usage:
    @evoloop_tool
    def my_tool(args, config: RunnableConfig): ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Log the error here if needed
            return f"Error: {str(e)}"
    
    # Apply LangChain's @tool
    return langchain_tool(wrapper)
