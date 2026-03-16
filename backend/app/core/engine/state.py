import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ClipboardItem(TypedDict):
    """
    Standardized item for the Workspace Clipboard.
    """
    content: Any  # Text, path to image, or element bounds
    mime_type: str  # "text/plain", "image/png", "application/json"
    metadata: dict[str, Any]
    created_at: float


class WorkspaceContext(TypedDict):
    """
    Universal workspace context cache to reduce redundant IO.
    """
    structure: str | None
    structure_updated_at: float | None  # Timestamp


class AgentConfig(TypedDict):
    """
    Blueprint for a Dynamic Sub-Agent.
    """
    role_name: str
    system_instructions: str
    tools: list[str]  # List of tool names to hydrate
    model_override: str | None  # Optional model override (e.g. "gpt-4o")
    namespace_context: str | None  # Track 8: Dynamic SOP namespace mounting


class ExecutionTicket(TypedDict):
    """
    Structured mission ticket for any Specialist Node.
    """
    ticket_type: str  # e.g., "bugfix", "web_research", "wiki_update"
    priority: str
    acceptance_criteria: list[str]

    # Target-specific context
    focus_paths: list[str] | None  # Primary for Operator/Documenter
    topic: str | None              # Primary for Researcher

    # Catch-all for specialized parameters
    parameters: dict[str, Any] | None

    # Dynamic Agent Configuration (v4.0)
    agent_config: AgentConfig | None

    constraints: list[str] | None
    expected_outcomes: list[str] | None

    # Track 8: Deterministic SOP Routing
    namespace_context: str | None


class RetrievalContext(TypedDict):
    repo_id: int
    files: list[str]  # Paths
    snippets: list[str]  # Content or summaries


class HITLState(TypedDict):
    """
    Human-in-the-Loop state for managing interrupts and user interactions.

    This is a generic structure that replaces task-specific fields like `pending_wiki_plan`.
    """

    request_id: str  # Unique ID for this HITL request
    request_type: str  # "approval", "input", "confirmation"
    resume_node: str  # Node to resume after user responds
    context: dict[str, Any]  # Node-specific context (e.g., wiki plan, file changes)
    created_at: str | None  # ISO timestamp


class BlackboardState(TypedDict):
    """
    Unified task and state management (Phase 4).
    Consolidates Ticket, Scratchpad, and Verification.
    """
    ticket: ExecutionTicket | None
    verification: dict[str, Any] | None
    route_reason: str | None
    
    # [NEW] Unified Dynamic Fields
    metadata: dict[str, Any]
    clipboard: list[ClipboardItem]
    visited_nodes: list[str]
    working_directory: str | None
    
    # [NEW] Parallel Execution State
    spawn_plan: dict[str, Any] | None
    pending_aggregation: dict[str, Any] | None
    subtask_results: list[dict[str, Any]]
    
    # [NEW] Planning State
    plan_approved: bool


class AgentState(TypedDict):
    # Conversation history (append-only)
    messages: Annotated[list[BaseMessage], add_messages]

    # Project Scope
    project_id: int | None

    # Current Plan / Intent
    current_plan: str | None
    structured_plan: str | None  # JSON string of domain.planning.models.Plan

    # Context retrieved by Researcher
    context: RetrievalContext | None

    # [NEW] Shared Workspace Context Cache
    workspace_context: WorkspaceContext | None

    # Execution artifacts (e.g. documents, code snippets)
    execution_artifact: str | None

    # [NEW Phase 4] Unified Blackboard
    blackboard: Annotated[BlackboardState | None, operator.ior]

    # Loop Control
    iteration_count: int
    error: str | None
    next_node: Annotated[str | None, lambda a, b: b]

    # [DEPRECATED v5] Deep Research State
    # These fields were used by the standalone DeepResearchEngine (now removed).
    # Worker uses ExecutionTicket.topic + max_steps instead.
    # Kept for LangGraph checkpoint schema compatibility — do NOT add new usages.
    research_loop_count: Annotated[int | None, lambda a, b: b]  # deprecated
    research_logs: Annotated[list[str] | None, operator.add]  # deprecated
    research_topic: str | None  # deprecated
    max_research_iterations: int | None  # deprecated

    # Memory
    user_preferences: str | None

    # Planning
    situation_analysis: str | None
    action_plan: str | None

    # Skill Execution (Imitation Learning Phase 3/4)
    skill_execution_attempted: bool | None

    # Tool Orchestration (Phase 3.0)
    active_tool_profile: str | None  # e.g. "DEVOPS", "RESEARCH"

    # Human-in-the-Loop State (Generic)
    # Used by documenter and other nodes for HITL flow
    # Wiki plan is stored in hitl_state.context["wiki_plan"]
    hitl_state: HITLState | None

    # Tool History (for finish node knowledge harvesting)
    tool_history: Annotated[list[str], operator.add]
