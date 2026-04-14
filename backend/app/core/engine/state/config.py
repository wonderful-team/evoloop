"""Agent runtime configuration and execution tickets."""
from typing import Any

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class TicketParameters(DynamicBaseModel):
    pass


class AgentRuntimeConfig(DynamicBaseModel):
    """Blueprint for a Dynamic Sub-Agent."""
    role_name: str
    system_instructions: str
    tools: list[str]
    model_override: str | None = None
    namespace_context: str | None = None
    is_subtask: bool = False
    subtask_context: dict = Field(default_factory=dict)
    skill_hint: str | None = None


class ExecutionTicket(DynamicBaseModel):
    """Structured mission ticket for any Specialist Node."""
    ticket_type: str
    priority: str = "normal"
    acceptance_criteria: list[str] = Field(default_factory=list)
    focus_paths: list[str] | None = None
    topic: str | None = None
    parameters: TicketParameters | None = None
    macro_goal: str | None = None
    agent_config: AgentRuntimeConfig | None = None
    constraints: list[str] | None = None
    expected_outcomes: list[str] | None = None
    namespace_context: str | None = None
    # Subtask / routing extensions
    parent_task_id: str | None = None
    subtask_id: str | None = None
    historical_context: Any | None = None
    referenced_tech: Any | None = None
    # Skill routing
    skill_id: str | None = None
    skill_ids: list[str] | None = None
    workflow_mode: str | None = None
    mcp_servers_required: list[str] = Field(default_factory=list)
    reason: str | None = None
