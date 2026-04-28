"""
State management tools for orchestration.
"""

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine.tools.orchestration.schemas import OrchestrationToolResult
from app.core.tools import evoloop_tool


@evoloop_tool(
    is_state_mutating=True,
    is_hidden=True,  # Internal state management, not user-facing
    name_map={"zh": "管理会话元数据", "en": "Manage Session Metadata"}
)
def manage_session_metadata(key: str, value: Any, _config: RunnableConfig) -> OrchestrationToolResult:
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
    return OrchestrationToolResult(
        status="success",
        message=f"Session metadata '{key}' updated successfully.",
        _signal="update_session_metadata",
        data={"key": key, "value": value}
    )
