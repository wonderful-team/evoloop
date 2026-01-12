import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class RetrievalContext(TypedDict):
    repo_id: int
    files: list[str]  # Paths
    snippets: list[str]  # Content or summaries


class HITLState(TypedDict):
    """
    Human-in-the-Loop state for managing interrupts and user interactions.
    
    This is a generic structure that replaces task-specific fields like `pending_wiki_plan`.
    """
    request_id: str                 # Unique ID for this HITL request
    request_type: str               # "approval", "input", "confirmation"
    resume_node: str                # Node to resume after user responds
    context: dict[str, Any]         # Node-specific context (e.g., wiki plan, file changes)
    created_at: str | None       # ISO timestamp


class AgentState(TypedDict):
    # Conversation history (append-only)
    messages: Annotated[list[BaseMessage], add_messages]

    # Project Scope
    project_id: int | None

    # Current Plan / Intent
    current_plan: str | None
    structured_plan: str | None # JSON string of domain.planning.models.Plan

    # Context retrieved by Researcher
    context: RetrievalContext | None

    # Code generated (diff or content)
    generated_code: str | None

    # Test Reuslts
    test_results: str | None

    # Loop Control
    iteration_count: int
    error: str | None
    next_node: Annotated[str | None, lambda a, b: b]

    # Deep Research State
    research_loop_count: Annotated[int | None, lambda a, b: b]
    research_logs: Annotated[list[str] | None, operator.add]
    research_topic: str | None
    parallel_research_tasks: list[str] | None
    max_research_iterations: int | None

    # Memory
    user_preferences: str | None

    # Planning
    technical_analysis: str | None
    implementation_plan: str | None

    # [NEW] Dynamic State Store
    # A dictionary to hold arbitrary variables (e.g. "loop_index", "api_status", "summary_draft")
    scratchpad: Annotated[dict[str, Any], operator.ior]

    # Skill Execution (Imitation Learning Phase 3/4)
    skill_execution_attempted: bool | None

    # Tool Orchestration (Phase 3.0)
    active_tool_profile: str | None # e.g. "DEVOPS", "RESEARCH"
    tool_retrieval_query: str | None # e.g. "kubernetes tools"

    # Human-in-the-Loop State (Generic)
    # Used by documenter and other nodes for HITL flow
    # Wiki plan is stored in hitl_state.context["wiki_plan"]
    hitl_state: HITLState | None

