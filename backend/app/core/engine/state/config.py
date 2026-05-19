from __future__ import annotations
"""Agent runtime configuration and execution tickets."""
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.core.engine.state.workspace import SubtaskContext
from app.infrastructure.pydantic_base import DynamicBaseModel


class RunnableConfigMetadata(DynamicBaseModel):
    """Metadata extracted from LangGraph RunnableConfig."""
    thread_id: str = "unknown"
    user_id: str | None = None
    project_id: int | None = None
    run_id: str | None = None
    model: str | None = None

    @classmethod
    def from_config(cls, config: dict | Any) -> RunnableConfigMetadata:
        """Hydrate metadata from a raw RunnableConfig dictionary."""
        if not config:
            return cls()
        
        # RunnableConfig is usually a dict, but let's be safe
        configurable = config if isinstance(config, dict) else getattr(config, "configurable", {})
        if isinstance(config, dict):
            configurable = config.get("configurable", {})
            if not configurable: # Fallback for flat dicts if any
                configurable = config

        return cls(
            thread_id=str(configurable.get("thread_id", "unknown")),
            user_id=configurable.get("user_id"),
            project_id=configurable.get("project_id"),
            run_id=configurable.get("run_id"),
            model=configurable.get("model"),
        )


class TicketParameters(DynamicBaseModel):
    task_steps: list[str] | None = None
    fallback_strategy: str | None = None
    target_apps: list[str] | None = None
    lazy_hydration: bool = False
    verbose_output: bool = True
    dependencies: list[str] | None = None


class WorkflowContext(DynamicBaseModel):
    step_number: int | None = None
    total_steps: int | None = None
    is_first_step: bool | None = None
    is_last_step: bool | None = None
    previous_results: list[Any] = Field(default_factory=list)
    current_skill: dict[str, Any] | None = None


class AgentRuntimeConfig(DynamicBaseModel):
    """Blueprint for a Dynamic Sub-Agent."""
    role_name: str = ""
    system_instructions: str = ""
    tools: list[str] = []
    model_override: str | None = None
    namespace_context: str | None = None
    is_subtask: bool = False
    subtask_context: SubtaskContext | None = None
    skill_hint: str | None = None

    @field_validator("tools", mode="before")
    @classmethod
    def _ensure_tools_list(cls, v):
        if v is None:
            return []
        return v


class ExecutionTicket(DynamicBaseModel):
    """Structured mission ticket for any Specialist Node."""
    ticket_type: str
    priority: str = "normal"
    acceptance_criteria: list[str] | None = Field(default_factory=list)
    focus_paths: list[str] | None = None
    topic: str
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
    skill_ids: list[int | str] | None = None
    workflow_mode: str | None = None
    mcp_servers_required: list[str] = Field(default_factory=list)
    reason: str | None = None
    complexity: str | None = None
    workflow_context: WorkflowContext | None = None
    is_resuming: bool = Field(default=False)

    @field_validator("topic", mode="before")
    @classmethod
    def _topic_must_be_non_empty(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("ExecutionTicket.topic cannot be empty or missing. Check upstream caller (route_to, decompose_task, etc.) to ensure a non-empty topic/intent/reason is provided.")
        return v.strip()

    @model_validator(mode="after")
    def _normalize_ticket_skills(self):
        if self.skill_ids and not self.workflow_mode:
            self.workflow_mode = "single" if len(self.skill_ids) <= 1 else "sequential"
        return self
