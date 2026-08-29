"""Agent runtime configuration and execution tickets."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from app.infrastructure.pydantic_base import DynamicBaseModel


class RunnableConfigMetadata(DynamicBaseModel):
    """Metadata extracted from the engine run context."""

    thread_id: str = "unknown"
    member_id: int | None = None
    project_id: int | None = None
    run_id: str | None = None
    model: str | None = None

    @classmethod
    def from_config(cls, config: dict) -> RunnableConfigMetadata:
        """Hydrate metadata from a config dictionary."""
        if not config:
            return cls()

        configurable = config.get("configurable", {}) or {}
        if not configurable:
            configurable = config

        metadata = config.get("metadata", {}) or {}

        project_id = configurable.get("project_id")
        if project_id is None:
            project_id = metadata.get("project_id")

        return cls(
            thread_id=str(configurable.get("thread_id", "unknown")),
            member_id=configurable.get("member_id"),
            project_id=project_id,
            run_id=configurable.get("run_id"),
            model=configurable.get("model"),
        )


class TicketParameters(DynamicBaseModel):
    dependencies: list[str] | None = None
    verbose_output: bool = True


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
    needs_audit: bool = Field(
        default=False,
        description="When True the Worker delivery is audited by the Reviewer (Finish) after completion (worker-delegation-design.md Phase C.5). Default False = present directly without audit.",
    )

    @field_validator("topic", mode="before")
    @classmethod
    def _topic_must_be_non_empty(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError(
                "ExecutionTicket.topic cannot be empty or missing. Check upstream caller (route_to, etc.) to ensure a non-empty topic/intent/reason is provided."
            )
        return v.strip()

    @model_validator(mode="after")
    def _normalize_ticket_skills(self):
        if self.skill_ids and not self.workflow_mode:
            self.workflow_mode = "single" if len(self.skill_ids) <= 1 else "sequential"
        return self
