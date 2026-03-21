"""
TraceParser Module - Phase 2 of Imitation Learning

This module transforms raw TraceEvent records into structured TraceSequence
objects that can be analyzed for pattern recognition and workflow synthesis.

Key Concepts:
- TraceStep: A single semantic step (action + observation + context)
- TraceSequence: An ordered list of TraceSteps representing a task
- Supports both agent-initiated and human-initiated actions
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sqlalchemy import select

from app.infrastructure.database.sql.database import session_scope
from app.models import TraceEvent

logger = logging.getLogger(__name__)


class ActionSource(str, Enum):
    """Who initiated the action."""

    AGENT = "agent"
    HUMAN = "human"


class ActionCategory(str, Enum):
    """High-level categorization of actions."""

    NAVIGATION = "navigation"  # File/URL navigation
    EDIT = "edit"  # Content modification
    QUERY = "query"  # Information retrieval
    COMMAND = "command"  # System command execution
    INTERACTION = "interaction"  # UI interaction
    DECISION = "decision"  # Approval/choice
    SYSTEM_INTERACTION = "system_interaction"  # Global system interaction
    OTHER = "other"


@dataclass
class UIContext:
    """Visual/UI context at the time of action."""

    screenshot_path: str | None = None
    element_selector: str | None = None
    element_text: str | None = None


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
    action_args: dict[str, Any] = field(default_factory=dict)

    # Observation/result
    observation: str | None = None
    success: bool = True

    # Context
    node_name: str = "unknown"
    state_context: dict[str, Any] = field(default_factory=dict)
    ui_context: UIContext | None = None

    # Metadata
    timestamp: float | None = None
    user_feedback: str | None = None


@dataclass
class TraceSequence:
    """
    A complete sequence of steps representing a task.
    Can be used for pattern analysis and workflow synthesis.
    """

    thread_id: str
    session_id: str | None = None
    task_name: str | None = None

    steps: list[TraceStep] = field(default_factory=list)

    # Derived metadata
    tools_used: list[str] = field(default_factory=list)
    has_human_intervention: bool = False
    success: bool = True

    def summarize(self) -> dict[str, Any]:
        """Generate a summary for LLM consumption."""
        return {
            "thread_id": self.thread_id,
            "task_name": self.task_name,
            "total_steps": len(self.steps),
            "human_steps": sum(1 for s in self.steps if s.source == ActionSource.HUMAN),
            "agent_steps": sum(1 for s in self.steps if s.source == ActionSource.AGENT),
            "tools_used": list(set(self.tools_used)),
            "success": self.success,
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

    # Tool-specific category overrides (Phase 18: Added atomic file tools)
    TOOL_CATEGORY_MAP = {
        "read_file": ActionCategory.QUERY,
        "write_file": ActionCategory.EDIT,
        "edit_file": ActionCategory.EDIT,
        "list_files": ActionCategory.QUERY,
        "file_system": ActionCategory.EDIT,
        "search_codebase": ActionCategory.QUERY,
        "search_web": ActionCategory.QUERY,
        "bash": ActionCategory.COMMAND,
        "git_operations": ActionCategory.COMMAND,
        "navigate_directory": ActionCategory.NAVIGATION,
        # Phase: Platform Control Integration
        "mobile_control": ActionCategory.SYSTEM_INTERACTION,
        "desktop_control": ActionCategory.SYSTEM_INTERACTION,
    }

    def __init__(self, thread_id: str, session_id: str | None = None):
        self.thread_id = thread_id
        self.session_id = session_id

    async def parse(self) -> TraceSequence:
        """
        Fetch TraceEvents and convert to TraceSequence.
        """
        events = await self._fetch_events()
        return self._convert_to_sequence(events)

    async def _fetch_events(self) -> list[TraceEvent]:
        """Fetch trace events from database."""
        async with session_scope() as session:
            stmt = (
                select(TraceEvent)
                .where(TraceEvent.thread_id == self.thread_id)
                .order_by(TraceEvent.step_number)
            )

            # Optionally filter by session
            if self.session_id:
                stmt = stmt.where(TraceEvent.recording_session_id == self.session_id)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    def _convert_to_sequence(self, events: list[TraceEvent]) -> TraceSequence:
        """Convert raw events to structured sequence."""
        sequence = TraceSequence(thread_id=self.thread_id, session_id=self.session_id)

        for event in events:
            if event.source == "global":
                step = self._parse_global_event(event)
            else:
                step = self._parse_event(event)

            if step:
                sequence.steps.append(step)

                # Track metadata
                if step.source == ActionSource.HUMAN:
                    sequence.has_human_intervention = True
                if step.action_name and step.category in [
                    ActionCategory.QUERY,
                    ActionCategory.EDIT,
                    ActionCategory.COMMAND,
                ]:
                    sequence.tools_used.append(step.action_name)

        return sequence

    def _parse_global_event(self, event: TraceEvent) -> TraceStep:
        """Parse a global observation event."""
        # Map event types to readable actions for LLM
        action_mapping = {
            "key_press": "key_press",
            "mouse_click": "click",
            "window_change": "window_change"
        }

        # Check for Mirror (scrcpy) interactions
        # If the click happens inside the scrcpy window, we convert it to a mobile_control action
        is_mirror = event.window_title and ("EvoLoop Mirror" in event.window_title or "scrcpy" in event.window_title.lower())

        # Construct meaningful action name
        app_prefix = f"[{event.app_name}] " if event.app_name else ""
        action_name = f"{app_prefix}{action_mapping.get(event.action_type, event.action_type)}"

        # Build args
        action_args = {}
        if event.key_name:
            action_args["key"] = event.key_name
        if event.mouse_button:
            action_args["button"] = event.mouse_button
        if event.mouse_x is not None:
            action_args["position"] = (event.mouse_x, event.mouse_y)

        # Mirror Normalization Logic
        if is_mirror:
            window_bounds = None
            if event.action_payload:
                try:
                    payload = json.loads(event.action_payload)
                    window_bounds = payload.get("window_bounds")
                except:
                    pass

            if window_bounds and len(window_bounds) == 4 and event.action_type in ("mouse_click", "click"):
                wx, wy, ww, wh = window_bounds
                if ww > 0 and wh > 0:
                    nx = (event.mouse_x - wx) / ww
                    ny = (event.mouse_y - wy) / wh

                    # Ensure it's within bounds
                    if 0 <= nx <= 1 and 0 <= ny <= 1:
                        return TraceStep(
                            step_number=event.step_number,
                            source=ActionSource.HUMAN,
                            category=ActionCategory.SYSTEM_INTERACTION,
                            action_type="tool_call",
                            action_name="mobile_control",
                            action_args={"action": "tap", "x": round(nx, 3), "y": round(ny, 3)},
                            node_name="mobile_interaction",
                            state_context={
                                "window_title": event.window_title,
                                "is_mirrored": True
                            },
                            timestamp=event.timestamp or 0.0
                        )

        mapped_action_type = action_mapping.get(event.action_type, event.action_type)
        return TraceStep(
            step_number=event.step_number,
            source=ActionSource.HUMAN,
            category=ActionCategory.SYSTEM_INTERACTION,
            action_type=mapped_action_type,
            action_name=action_name,
            action_args=action_args,
            node_name="global_observation",
            state_context={
                "window_title": event.window_title,
                "app_name": event.app_name,
            },
            timestamp=event.timestamp or 0.0
        )

    def _parse_event(self, event: TraceEvent) -> TraceStep | None:
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
            if (
                event.ui_element_info
                or event.screenshot_path
                or event.target_selector
                or event.target_text
            ):
                ui_info = (
                    json.loads(event.ui_element_info) if event.ui_element_info else {}
                )
                ui_context = UIContext(
                    screenshot_path=event.screenshot_path,
                    element_selector=event.target_selector or ui_info.get("selector"),
                    element_text=event.target_text or ui_info.get("text"),
                )

            # Parse state context (simplified for synthesis)
            state_context = {}
            if event.state_snapshot:
                try:
                    state_context = json.loads(event.state_snapshot)
                except Exception:
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
                user_feedback=event.user_feedback,
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
        try:
            from app.utils import render_template
            return render_template(
                "events/trace_narrative.prompt.j2",
                thread_id=sequence.thread_id,
                task_name=sequence.task_name,
                steps=sequence.steps,
                has_human_intervention=sequence.has_human_intervention
            )
        except Exception as e:
            logger.error(f"Failed to render Trace narrative: {e}")
            # Minimal fallback
            return f"Trace Narrative for {sequence.thread_id} (Error rendering template)"
