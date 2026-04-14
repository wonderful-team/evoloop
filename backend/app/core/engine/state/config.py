"""Agent runtime configuration and execution tickets."""
from typing import Any, List, Optional

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class TicketParameters(DynamicBaseModel):
    pass


class AgentRuntimeConfig(DynamicBaseModel):
    """Blueprint for a Dynamic Sub-Agent."""
    role_name: str
    system_instructions: str
    tools: List[str]
    model_override: Optional[str] = None
    namespace_context: Optional[str] = None
    is_subtask: bool = False
    subtask_context: dict = Field(default_factory=dict)
    skill_hint: Optional[str] = None


class ExecutionTicket(DynamicBaseModel):
    """Structured mission ticket for any Specialist Node."""
    ticket_type: str
    priority: str = "normal"
    acceptance_criteria: List[str] = Field(default_factory=list)
    focus_paths: Optional[List[str]] = None
    topic: Optional[str] = None
    parameters: Optional[TicketParameters] = None
    macro_goal: Optional[str] = None
    agent_config: Optional[AgentRuntimeConfig] = None
    constraints: Optional[List[str]] = None
    expected_outcomes: Optional[List[str]] = None
    namespace_context: Optional[str] = None
    # Subtask / routing extensions
    parent_task_id: Optional[str] = None
    subtask_id: Optional[str] = None
    historical_context: Optional[Any] = None
    referenced_tech: Optional[Any] = None
    # Skill routing
    skill_id: Optional[str] = None
    skill_ids: Optional[List[str]] = None
    workflow_mode: Optional[str] = None
    mcp_servers_required: List[str] = Field(default_factory=list)
    reason: Optional[str] = None
