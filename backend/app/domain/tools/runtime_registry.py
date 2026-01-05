
from typing import Dict, List
from langchain_core.tools import BaseTool

_RUNTIME_TOOLS: Dict[str, BaseTool] = {}

def register_runtime_tool(tool: BaseTool) -> None:
    """
    Registers a new tool created at runtime.
    """
    _RUNTIME_TOOLS[tool.name] = tool

def get_runtime_tools() -> List[BaseTool]:
    return list(_RUNTIME_TOOLS.values())
