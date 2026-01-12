from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool


@tool
def update_scratchpad(key: str, value: Any, config: RunnableConfig) -> str:
    """
    Updates the agent's dynamic state (scratchpad) with a key-value pair.
    Useful for passing information between nodes or controlling flow (routers).
    
    Args:
        key: The variable name to set (e.g., "complexity", "status").
        value: The value to assign (can be string, number, boolean, etc.).
    """
    # NOTE: Special Handling in GenericLLMNode
    # This tool is recognized by the `generic_node` execution loop.
    # When `generic_node` sees a call to `update_scratchpad`, it extracts the key/value
    # and includes them in the returned state dictionary under "scratchpad".
    # This enables the tool to mutate the global graph state.

    return f"State updated: {key}={value}"
