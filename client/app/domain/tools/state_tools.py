from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.tools import evoloop_tool


@evoloop_tool(is_state_mutating=True)
def update_scratchpad(key: str, value: Any, _config: RunnableConfig) -> str:
    """
    Updates the agent's dynamic state (scratchpad) with a key-value pair.
    Useful for passing information between nodes or controlling flow (routers).

    Args:
        key: The variable name to set (e.g., "complexity", "status").
        value: The value to assign (can be string, number, boolean, etc.).
    """
    # NOTE: Special Handling in GenericLLMNode
    return f"State updated: {key}={value}"


@evoloop_tool(is_state_mutating=True)
def manage_session_metadata(key: str, value: Any, _config: RunnableConfig) -> str:
    """
    Updates session-level metadata to guide the agent's behavior and context resolution.
    
    Common keys:
    - 'current_ecosystem': Set to 'android', 'macos', or 'web' based on telemetry.
    - 'user_persona': Describe the user style or specific domain expertise needed.
    - 'priority': 'low', 'normal', 'high', 'emergency'.
    
    Args:
        key: The metadata key to set.
        value: The value to assign.
    """
    # Managed similarly to scratchpad in the global context
    return f"Session metadata set: {key}={value}"
