import logging
import operator
import time
from typing import Annotated, Any, Dict, List, Optional, Union, TypedDict
from pydantic import BaseModel, Field

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.utils.model_helpers import LegacyDictMixin

logger = logging.getLogger(__name__)


class ClipboardItem(BaseModel, LegacyDictMixin):
    """
    Standardized item for the Workspace Clipboard.
    """
    content: Any  # Text, path to image, or element bounds
    mime_type: str  # "text/plain", "image/png", "application/json"
    metadata: Dict[str, Any] = Field(default_factory=dict)
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
    parameters: Optional[Dict[str, Any]] = None

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
    context: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class BlackboardState(BaseModel, LegacyDictMixin):
    """
    Unified task and state management.
    """
    ticket: Optional[ExecutionTicket] = None
    verification: Optional[Dict[str, Any]] = None
    route_reason: Optional[str] = None
    
    # Unified Dynamic Fields
    metadata: Dict[str, Any] = Field(default_factory=dict)
    clipboard: List[ClipboardItem] = Field(default_factory=list)
    visited_nodes: List[str] = Field(default_factory=list)
    working_directory: Optional[str] = None
    
    # Parallel Execution State
    spawn_plan: Optional[Dict[str, Any]] = None
    pending_aggregation: Optional[Dict[str, Any]] = None
    subtask_results: List[Dict[str, Any]] = Field(default_factory=list)
    
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


class AgentState(TypedDict):
    """
    Top-level Agent State for LangGraph.
    Uses TypedDict for compatibility with LangGraph's message history and reducers.
    """
    # Conversation history
    messages: Annotated[List[BaseMessage], add_messages]

    # Thread tracking
    thread_id: Optional[str]
    is_retry: Optional[bool]

    # Project Scope
    project_id: Optional[int]

    # Current Plan
    current_plan: Optional[str]
    structured_plan: Optional[str]  # JSON string

    # Domain Context
    context: Optional[RetrievalContext]
    workspace_context: Optional[WorkspaceContext]
    execution_artifact: Optional[str]

    # Unified Blackboard with custom reducer
    blackboard: Annotated[Optional[BlackboardState], merge_blackboard]

    # Loop Control
    iteration_count: int
    error: Optional[str]
    next_node: Annotated[Optional[str], lambda a, b: b]
    
    # Execution Ticket for mission context
    execution_ticket: Optional[ExecutionTicket]

    # Memory
    user_preferences: Optional[str]
    situation_analysis: Optional[str]
    action_plan: Optional[str]

    # Skill Execution
    skill_execution_attempted: Optional[bool]
    active_tool_profile: Optional[str]

    # Human-in-the-Loop State (Generic)
    hitl_state: Optional[HITLState]

    # Tool History
    tool_history: Annotated[List[str], operator.add]
