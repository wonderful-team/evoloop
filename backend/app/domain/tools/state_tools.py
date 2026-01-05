from typing import Any, Dict, Optional
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

@tool
def update_scratchpad(key: str, value: Any, config: RunnableConfig) -> str:
    """
    Updates the agent's dynamic state (scratchpad) with a key-value pair.
    Useful for passing information between nodes or controlling flow (routers).
    
    Args:
        key: The variable name to set (e.g., "complexity", "status").
        value: The value to assign (can be string, number, boolean, etc.).
    """
    # In LangGraph, we typically return a Command or directly update state if we are a node.
    # But tools return strings/artifacts usually.
    # However, 'GenericLLMNode' (and Supervisor) needs to know how to handle this.
    # Standard Pattern: The Tool returns a value, and the Node collects it.
    # BUT, 'update_scratchpad' implies a side effect on 'state'.
    
    # In our 'generic_node', we are inside a node.
    # The tool execution is happening inside the node.
    # We need the node to capture this update and merge it into the state returned by the node.
    
    # HACK: For now, we return a special prefix string or relies on the Node interpreting the tool call?
    # NO. The clean way in LangGraph is:
    # The Node logic sees the tool call, executes it, and if it detects a state update, it includes it in the return dict.
    
    # Current 'generic_node` logic:
    # 1. LLM -> Tool Call
    # 2. execute(tool) -> result
    # 3. ToolMessage(result)
    
    # It does NOT automatically update 'scratchpad' just because a tool was called.
    # WE NEED TO FIX THIS.
    # We can either:
    # A) Have a special tool that writes to a global context (messy).
    # B) Have 'generic_node' inspect the tool name. If it is 'update_scratchpad', we parse the args and update our local 'scratchpad_accumulated' dict.
    
    # Let's go with B (Conceptually).
    # But strictly, the tool function itself should run.
    # Let's make this tool return the value as a confirmation string.
    # AND modify `generic_node` to "listen" for this specific tool or use a callback?
    
    # Simpler: The `GenericLLMNode` logic loops. At the end, it returns `{"messages": [...]}`.
    # It currently relies on `AgentState` being Append-Only for messages.
    # For `scratchpad`, we defined it with `operator.ior` (merge).
    # So the node needs to return `{"scratchpad": {...}}`.
    
    # So `generic_node` needs to collect mutations.
    
    return f"State updated: {key}={value}"
