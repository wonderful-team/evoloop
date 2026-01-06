"""
TraceParser Module - Phase 2 of Imitation Learning

This module transforms raw TraceEvent records into structured TraceSequence
objects that can be analyzed for pattern recognition and workflow synthesis.

Key Concepts:
- TraceStep: A single semantic step (action + observation + context)
- TraceSequence: An ordered list of TraceSteps representing a task
- Supports both agent-initiated and human-initiated actions
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
from sqlalchemy import select
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models import TraceEvent

logger = logging.getLogger("evoloop.learning.parser")


class ActionSource(str, Enum):
    """Who initiated the action."""
    AGENT = "agent"
    HUMAN = "human"


class ActionCategory(str, Enum):
    """High-level categorization of actions."""
    NAVIGATION = "navigation"  # File/URL navigation
    EDIT = "edit"              # Content modification
    QUERY = "query"            # Information retrieval
    COMMAND = "command"        # System command execution
    INTERACTION = "interaction"  # UI interaction
    DECISION = "decision"      # Approval/choice
    OTHER = "other"


@dataclass
class UIContext:
    """Visual/UI context at the time of action."""
    screenshot_path: Optional[str] = None
    element_selector: Optional[str] = None
    element_text: Optional[str] = None


@dataclass
class TraceStep:
    """
    A single semantic step in a trace sequence.
    Represents one complete action-observation pair.
    """
    step_number: int
    source: ActionSource
    category: ActionCategory
    
    # Core action info
    action_type: str  # Raw type (tool_call, click, input, etc.)
    action_name: str  # Semantic name (e.g., "read_file", "click_button")
    action_args: Dict[str, Any] = field(default_factory=dict)
    
    # Observation/result
    observation: Optional[str] = None
    success: bool = True
    
    # Context
    node_name: str = "unknown"
    state_context: Dict[str, Any] = field(default_factory=dict)
    ui_context: Optional[UIContext] = None
    
    # Metadata
    timestamp: Optional[float] = None
    user_feedback: Optional[str] = None


@dataclass
class TraceSequence:
    """
    A complete sequence of steps representing a task.
    Can be used for pattern analysis and workflow synthesis.
    """
    thread_id: str
    session_id: Optional[str] = None
    task_name: Optional[str] = None
    
    steps: List[TraceStep] = field(default_factory=list)
    
    # Derived metadata
    tools_used: List[str] = field(default_factory=list)
    has_human_intervention: bool = False
    success: bool = True
    
    def summarize(self) -> Dict[str, Any]:
        """Generate a summary for LLM consumption."""
        return {
            "thread_id": self.thread_id,
            "task_name": self.task_name,
            "total_steps": len(self.steps),
            "human_steps": sum(1 for s in self.steps if s.source == ActionSource.HUMAN),
            "agent_steps": sum(1 for s in self.steps if s.source == ActionSource.AGENT),
            "tools_used": list(set(self.tools_used)),
            "success": self.success
        }


class TraceParser:
    """
    Parses raw TraceEvent records into structured TraceSequence.
    """
    
    # Mapping of action types to categories
    CATEGORY_MAP = {
        "tool_call": ActionCategory.QUERY,  # Default, refined below
        "click": ActionCategory.INTERACTION,
        "input": ActionCategory.INTERACTION,
        "node_start": ActionCategory.OTHER,
        "llm_output": ActionCategory.DECISION,
    }
    
    # Tool-specific category overrides
    TOOL_CATEGORY_MAP = {
        "read_file": ActionCategory.QUERY,
        "manage_file": ActionCategory.EDIT,
        "search_codebase": ActionCategory.QUERY,
        "search_web": ActionCategory.QUERY,
        "bash": ActionCategory.COMMAND,
        "run_command": ActionCategory.COMMAND,
        "git_operations": ActionCategory.COMMAND,
        "navigate_directory": ActionCategory.NAVIGATION,
    }
    
    def __init__(self, thread_id: str, session_id: Optional[str] = None):
        self.thread_id = thread_id
        self.session_id = session_id
    
    async def parse(self) -> TraceSequence:
        """
        Fetch TraceEvents and convert to TraceSequence.
        """
        events = await self._fetch_events()
        return self._convert_to_sequence(events)
    
    async def _fetch_events(self) -> List[TraceEvent]:
        """Fetch trace events from database."""
        async with session_scope() as session:
            stmt = select(TraceEvent).where(
                TraceEvent.thread_id == self.thread_id
            ).order_by(TraceEvent.step_number)
            
            # Optionally filter by session
            if self.session_id:
                stmt = stmt.where(TraceEvent.recording_session_id == self.session_id)
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    def _convert_to_sequence(self, events: List[TraceEvent]) -> TraceSequence:
        """Convert raw events to structured sequence."""
        sequence = TraceSequence(
            thread_id=self.thread_id,
            session_id=self.session_id
        )
        
        for event in events:
            step = self._parse_event(event)
            if step:
                sequence.steps.append(step)
                
                # Track metadata
                if step.source == ActionSource.HUMAN:
                    sequence.has_human_intervention = True
                if step.action_name and step.category in [ActionCategory.QUERY, ActionCategory.EDIT, ActionCategory.COMMAND]:
                    sequence.tools_used.append(step.action_name)
        
        return sequence
    
    def _parse_event(self, event: TraceEvent) -> Optional[TraceStep]:
        """Convert a single TraceEvent to TraceStep."""
        try:
            # Determine source
            source = ActionSource.HUMAN if event.is_human_action else ActionSource.AGENT
            
            # Parse payload
            payload = json.loads(event.action_payload) if event.action_payload else {}
            
            # Determine action name and args
            action_name = event.action_type
            action_args = {}
            
            if event.action_type == "tool_call":
                action_name = payload.get("name", "unknown_tool")
                action_args = payload.get("args", {})
            elif event.action_type in ["click", "input"]:
                action_args = payload
            
            # Determine category
            category = self._categorize_action(event.action_type, action_name)
            
            # Build UI context if available
            ui_context = None
            ui_context = None
            if event.ui_element_info or event.screenshot_path or event.target_selector or event.target_text:
                ui_info = json.loads(event.ui_element_info) if event.ui_element_info else {}
                ui_context = UIContext(
                    screenshot_path=event.screenshot_path,
                    element_selector=event.target_selector or ui_info.get("selector"),
                    element_text=event.target_text or ui_info.get("text")
                )
            
            # Parse state context (simplified for synthesis)
            state_context = {}
            if event.state_snapshot:
                try:
                    state_context = json.loads(event.state_snapshot)
                except:
                    pass
            
            return TraceStep(
                step_number=event.step_number,
                source=source,
                category=category,
                action_type=event.action_type,
                action_name=action_name,
                action_args=action_args,
                node_name=event.node_name,
                state_context=state_context,
                ui_context=ui_context,
                user_feedback=event.user_feedback
            )
            
        except Exception as e:
            logger.error(f"Failed to parse event {event.id}: {e}")
            return None
    
    def _categorize_action(self, action_type: str, action_name: str) -> ActionCategory:
        """Determine the category of an action."""
        # Check tool-specific first
        if action_name in self.TOOL_CATEGORY_MAP:
            return self.TOOL_CATEGORY_MAP[action_name]
        
        # Fall back to action type
        return self.CATEGORY_MAP.get(action_type, ActionCategory.OTHER)
    
    def to_narrative(self, sequence: TraceSequence) -> str:
        """
        Convert sequence to human-readable narrative for LLM synthesis.
        """
        lines = [f"# Task Trace: {sequence.task_name or 'Untitled'}", ""]
        lines.append(f"**Thread ID**: {sequence.thread_id}")
        lines.append(f"**Total Steps**: {len(sequence.steps)}")
        lines.append(f"**Human Intervention**: {'Yes' if sequence.has_human_intervention else 'No'}")
        lines.append("")
        lines.append("## Steps")
        lines.append("")
        
        for step in sequence.steps:
            source_icon = "👤" if step.source == ActionSource.HUMAN else "🤖"
            lines.append(f"### Step {step.step_number} {source_icon} [{step.category.value}]")
            lines.append(f"- **Action**: `{step.action_name}`")
            
            if step.action_args:
                # Truncate long args
                args_str = json.dumps(step.action_args, default=str)
                if len(args_str) > 200:
                    args_str = args_str[:200] + "..."
                lines.append(f"- **Args**: `{args_str}`")
            
            if step.ui_context:
                if step.ui_context.element_text:
                    lines.append(f"- **UI Element**: \"{step.ui_context.element_text[:50]}\"")
                if step.ui_context.screenshot_path:
                    lines.append(f"- **Screenshot**: `{step.ui_context.screenshot_path}`")
            
            if step.user_feedback:
                lines.append(f"- **User Feedback**: \"{step.user_feedback}\"")
            
            lines.append("")
        
        return "\n".join(lines)
