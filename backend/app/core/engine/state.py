import logging
import operator
import time
from typing import Annotated, Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.utils.model_helpers import LegacyDictMixin

logger = logging.getLogger(__name__)


class TicketParameters(BaseModel, LegacyDictMixin):
    model_config = ConfigDict(extra="allow")


class MessagePayload(BaseModel, LegacyDictMixin):
    model_config = ConfigDict(extra="allow")


class HITLContext(BaseModel, LegacyDictMixin):
    model_config = ConfigDict(extra="allow")
    prompt: Optional[str] = None
    options: Optional[List[str]] = None
    default_value: Optional[str] = None
    allow_cancel: bool = True
    payload: MessagePayload = Field(default_factory=MessagePayload)


class ClipboardMetadata(BaseModel, LegacyDictMixin):
    model_config = ConfigDict(extra="allow")
    source_file: Optional[str] = None
    line_range: Optional[tuple[int, int]] = None


class SubtaskContext(BaseModel, LegacyDictMixin):
    model_config = ConfigDict(extra="allow")
    description: Optional[str] = None
    dependencies: Optional[List[str]] = None


class ClipboardItem(BaseModel, LegacyDictMixin):
    """
    Standardized item for the Workspace Clipboard.
    """
    model_config = ConfigDict(extra="allow")
    content: Any  # Text, path to image, or element bounds
    mime_type: str  # "text/plain", "image/png", "application/json"
    metadata: ClipboardMetadata = Field(default_factory=ClipboardMetadata)
    created_at: float = Field(default_factory=time.time)


class WorkspaceContext(BaseModel, LegacyDictMixin):
    """
    Universal workspace context cache to reduce redundant IO.
    """
    structure: Optional[str] = None
    structure_updated_at: Optional[float] = None  # Timestamp


class AgentConfig(BaseModel, LegacyDictMixin):
    """
    Blueprint for a Dynamic Sub-Agent.
    """
    role_name: str
    system_instructions: str
    tools: List[str]  # List of tool names to hydrate
    model_override: Optional[str] = None
    namespace_context: Optional[str] = None


class ExecutionTicket(BaseModel, LegacyDictMixin):
    """
    Structured mission ticket for any Specialist Node.
    """
    ticket_type: str  # e.g., "bugfix", "web_research", "wiki_update"
    priority: str = "normal"
    acceptance_criteria: List[str] = Field(default_factory=list)

    # Target-specific context
    focus_paths: Optional[List[str]] = None
    topic: Optional[str] = None

    # Catch-all for specialized parameters
    parameters: Optional[TicketParameters] = None

    # Macro context for subtasks
    macro_goal: Optional[str] = None

    # Dynamic Agent Configuration
    agent_config: Optional[AgentConfig] = None

    constraints: Optional[List[str]] = None
    expected_outcomes: Optional[List[str]] = None

    # Track 8: Deterministic SOP Routing
    namespace_context: Optional[str] = None


class RetrievalContext(BaseModel, LegacyDictMixin):
    repo_id: int
    files: List[str] = Field(default_factory=list)
    snippets: List[str] = Field(default_factory=list)


class HITLState(BaseModel, LegacyDictMixin):
    """
    Human-in-the-Loop state for managing interrupts and user interactions.
    """
    request_id: str
    request_type: str  # "approval", "input", "confirmation"
    resume_node: str
    context: HITLContext = Field(default_factory=HITLContext)
    created_at: Optional[str] = None


class BlackboardVerification(BaseModel, LegacyDictMixin):
    model_config = ConfigDict(extra="allow")
    status: str


class SpawnPlanSubtask(BaseModel, LegacyDictMixin):
    model_config = ConfigDict(extra="allow")
    id: str
    intent: str
    description: Optional[str] = None
    title: Optional[str] = None
    context: Optional[SubtaskContext] = None
    dependencies: Optional[List[str]] = None
    tools: Optional[List[str]] = None
    skill_hint: Optional[str] = None


class SpawnPlan(BaseModel, LegacyDictMixin):
    model_config = ConfigDict(extra="allow")
    subtasks: List[SpawnPlanSubtask] = Field(default_factory=list)
    _requires_aggregation: bool = True
    parent_task: str = ""
    aggregation_strategy: str = "merge"
    _routing_signal: Optional[str] = None


class PendingAggregation(BaseModel, LegacyDictMixin):
    model_config = ConfigDict(extra="allow")
    strategy: str
    expected_count: int
    actual_count: Optional[int] = None


class SubtaskResult(BaseModel, LegacyDictMixin):
    model_config = ConfigDict(extra="allow")
    subtask_id: str
    status: str
    result: Any
    tools_used: Optional[List[str]] = None
    timestamp: Optional[float] = None


class BlackboardMetadata(BaseModel, LegacyDictMixin):
    model_config = ConfigDict(extra="allow")


class BlackboardState(BaseModel, LegacyDictMixin):
    """
    Unified task and state management.
    """
    model_config = ConfigDict(extra="allow")
    ticket: Optional[ExecutionTicket] = None
    verification: Optional[BlackboardVerification] = None
    route_reason: Optional[str] = None
    
    # Unified Dynamic Fields
    metadata: BlackboardMetadata = Field(default_factory=BlackboardMetadata)
    clipboard: List[ClipboardItem] = Field(default_factory=list)
    visited_nodes: List[str] = Field(default_factory=list)
    working_directory: Optional[str] = None
    
    # Parallel Execution State
    spawn_plan: Optional[SpawnPlan] = None
    pending_aggregation: Optional[PendingAggregation] = None
    subtask_results: List[SubtaskResult] = Field(default_factory=list)
    
    # Planning State
    plan_approved: bool = False
    worker_outcome: Optional[str] = None


def merge_blackboard(old: Optional[BlackboardState], new: Union[BlackboardState, Dict[str, Any], None]) -> Optional[BlackboardState]:
    """
    Custom reducer for BlackboardState to handle parallel results safely.
    Supports both model instances and raw dictionaries.
    """
    if old is None:
        if isinstance(new, dict):
            return BlackboardState.model_validate(new)
        return new
    if new is None:
        return old

    # Ensure new is a dict for merging
    if isinstance(new, BaseModel):
        new_data = new.model_dump(exclude_unset=True)
    else:
        new_data = new

    # Create a copy of old data for merging
    merged_data = old.model_dump()

    # Standard field updates (overwrite)
    simple_fields = [
        "ticket", "verification", "route_reason", "spawn_plan", 
        "pending_aggregation", "working_directory", "plan_approved", "worker_outcome"
    ]
    for key in simple_fields:
        if key in new_data:
            merged_data[key] = new_data[key]

    # [CRITICAL] Parallel List Concatenation (Deduplicated)
    if "subtask_results" in new_data:
        old_results = merged_data.get("subtask_results") or []
        new_results = new_data["subtask_results"] or []
        if not new_results:
            merged_data["subtask_results"] = []
        else:
            seen_ids = {r.get("subtask_id") for r in old_results if r.get("subtask_id")}
            delta_results = []

            for r in new_results:
                sid = r.get("subtask_id")
                if not sid or sid not in seen_ids:
                    delta_results.append(r)
                else:
                    logger.debug(f"[State] ℹ️ Subtask ID collision/sync for '{sid}' - skipping duplicate.")
            
            merged_data["subtask_results"] = old_results + delta_results

    # Metadata & Clipboard Merges
    if "metadata" in new_data:
        old_meta = merged_data.get("metadata") or {}
        merged_data["metadata"] = {**old_meta, **new_data["metadata"]}
    
    if "visited_nodes" in new_data:
        old_nodes = merged_data.get("visited_nodes") or []
        new_nodes = new_data["visited_nodes"] or []
        # Preserve order while deduplicating
        combined = old_nodes + [n for n in new_nodes if n not in old_nodes]
        merged_data["visited_nodes"] = combined

    if "clipboard" in new_data:
        merged_data["clipboard"] = (merged_data.get("clipboard") or []) + new_data["clipboard"]

    return BlackboardState.model_validate(merged_data)


class StateUpdate(BaseModel, LegacyDictMixin):
    """
    Standardized state update returned by LangGraph nodes.
    Allows nodes to return typed partial updates to AgentState.
    """
    model_config = ConfigDict(extra="allow")

    messages: Optional[List[BaseMessage]] = None
    next_node: Optional[str] = None
    blackboard: Optional[BlackboardState] = None
    iteration_count: Optional[int] = None
    error: Optional[str] = None
    execution_ticket: Optional[ExecutionTicket] = None
    current_plan: Optional[str] = None
    structured_plan: Optional[str] = None
    situation_analysis: Optional[str] = None
    action_plan: Optional[str] = None
    skill_execution_attempted: Optional[bool] = None
    active_tool_profile: Optional[str] = None
    hitl_state: Optional[HITLState] = None
    tool_history: Optional[List[str]] = None
    project_id: Optional[int] = None
    context: Optional[RetrievalContext] = None
    workspace_context: Optional[WorkspaceContext] = None
    execution_artifact: Optional[str] = None


class AgentState(BaseModel, LegacyDictMixin):
    """
    Top-level Agent State for LangGraph.
    Uses Pydantic BaseModel for structured typing while preserving dict-like access.
    """
    model_config = ConfigDict(extra="allow")

    # Conversation history
    messages: Annotated[List[BaseMessage], add_messages] = Field(default_factory=list)

    # Thread tracking
    thread_id: Optional[str] = None
    is_retry: Optional[bool] = None

    # Project Scope
    project_id: Optional[int] = None

    # Current Plan
    current_plan: Optional[str] = None
    structured_plan: Optional[str] = None  # JSON string

    # Domain Context
    context: Optional[RetrievalContext] = None
    workspace_context: Optional[WorkspaceContext] = None
    execution_artifact: Optional[str] = None

    # Unified Blackboard with custom reducer
    blackboard: Annotated[Optional[BlackboardState], merge_blackboard] = None

    # Loop Control
    iteration_count: int = 0
    error: Optional[str] = None
    next_node: Annotated[Optional[str], lambda a, b: b] = None
    
    # Execution Ticket for mission context
    execution_ticket: Optional[ExecutionTicket] = None

    # Memory
    user_preferences: Optional[str] = None
    situation_analysis: Optional[str] = None
    action_plan: Optional[str] = None

    # Skill Execution
    skill_execution_attempted: Optional[bool] = None
    active_tool_profile: Optional[str] = None

    # Human-in-the-Loop State (Generic)
    hitl_state: Optional[HITLState] = None

    # Tool History
    tool_history: Annotated[List[str], operator.add] = Field(default_factory=list)
