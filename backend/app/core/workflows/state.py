from typing import TypedDict, Annotated, List, Union, Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
import operator


class RetrievalContext(TypedDict):
    repo_id: int
    files: List[str]  # Paths
    snippets: List[str]  # Content or summaries


class AgentState(TypedDict):
    # Conversation history (append-only)
    messages: Annotated[List[BaseMessage], add_messages]
    
    # Project Scope
    project_id: Optional[int]

    # Current Plan / Intent
    current_plan: Optional[str]
    structured_plan: Optional[str] # JSON string of domain.planning.models.Plan

    # Context retrieved by Researcher
    context: Optional[RetrievalContext]

    # Code generated (diff or content)
    generated_code: Optional[str]

    # Test Reuslts
    test_results: Optional[str]

    # Loop Control
    iteration_count: int
    error: Optional[str]
    next_node: Annotated[Optional[str], lambda a, b: b]

    # Deep Research State
    research_loop_count: Annotated[Optional[int], lambda a, b: b]
    research_logs: Annotated[Optional[List[str]], operator.add]
    research_topic: Optional[str]
    parallel_research_tasks: Optional[List[str]]
    max_research_iterations: Optional[int]

    # Memory
    user_preferences: Optional[str]

    # Planning
    technical_analysis: Optional[str]
    implementation_plan: Optional[str]
