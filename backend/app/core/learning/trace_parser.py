"""
TraceParser Module - Phase 2 of Imitation Learning

This module transforms raw TraceEvent records into structured TraceSequence
objects that can be analyzed for pattern recognition and workflow synthesis.

Key Concepts:
- TraceStep: A single semantic step (action + observation + context)
- TraceSequence: An ordered list of TraceSteps representing a task
- Supports both agent-initiated and human-initiated actions
"""

import logging

from pydantic import Field
from sqlalchemy import or_, select

from app.core.learning.constants import EVENT_CATEGORY_MAP, TOOL_CATEGORY_MAP
from app.core.learning.schemas import (
    ActionCategory,
    ActionSource,
    TraceStep,
    TraceSummary,
    UIContext,
)
from app.infrastructure.database import session_scope
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models import Message, TraceEvent

logger = logging.getLogger(__name__)


class TraceSequence(DynamicBaseModel):
    """
    A complete sequence of steps representing a task.
    Can be used for pattern analysis and workflow synthesis.
    """
    thread_id: str
    session_id: str | None = None
    task_name: str | None = None
    initial_intent: str | None = None # Captured from the first human message

    steps: list[TraceStep] = Field(default_factory=list)

    # Derived metadata
    tools_used: list[str] = Field(default_factory=list)
    has_human_intervention: bool = False
    success: bool = True

    def summarize(self) -> TraceSummary:
        """Generate a summary for LLM consumption."""
        return TraceSummary(
            thread_id=self.thread_id,
            task_name=self.task_name,
            total_steps=len(self.steps),
            human_steps=sum(1 for s in self.steps if s.source == ActionSource.HUMAN),
            agent_steps=sum(1 for s in self.steps if s.source == ActionSource.AGENT),
            tools_used=list(set(self.tools_used)),
            success=self.success,
        )


class TraceParser:
    """
    Parses raw TraceEvent records into structured TraceSequence.
    """

    def __init__(self, thread_id: str, session_id: str | None = None):
        self.thread_id = thread_id
        self.session_id = session_id

    async def parse(self) -> TraceSequence:
        """
        Fetch TraceEvents and convert to TraceSequence.
        """
        events = await self._fetch_events()
        intent = await self._fetch_initial_intent()
        sequence = self._convert_to_sequence(events)
        sequence.initial_intent = intent
        return sequence

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
                # Use unified session_id or legacy recording_session_id
                stmt = stmt.where(or_(
                    TraceEvent.session_id == self.session_id,
                    TraceEvent.recording_session_id == self.session_id
                ))

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def _fetch_initial_intent(self) -> str | None:
        """Fetch the first human message in the thread as the initial intent."""
        async with session_scope() as session:
            stmt = select(Message).where(
                Message.thread_id == self.thread_id,
                Message.role == "human"
            ).order_by(Message.created_at).limit(1)
            result = await session.execute(stmt)
            msg = result.scalar_one_or_none()
            return msg.content if msg else None

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

        # Construct meaningful action name
        app_prefix = f"[{event.app_name}] " if event.app_name else ""
        action_name = f"{app_prefix}{action_mapping.get(event.event_type, event.event_type)}"
        # Build args
        action_args = {}
        if event.key_name:
            action_args["key"] = event.key_name
        if event.mouse_button:
            action_args["button"] = event.mouse_button
        if event.mouse_x is not None:
            action_args["position"] = (event.mouse_x, event.mouse_y)

        mapped_event_type = action_mapping.get(event.event_type, event.event_type)
        return TraceStep(
            step_number=event.step_number,
            source=ActionSource.HUMAN,
            category=ActionCategory.SYSTEM_INTERACTION,
            action_type=mapped_event_type,
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

            # Payload is now a dict (from JSON column)
            payload = event.payload or {}

            # Determine action name and args
            action_name = event.event_type
            action_args = {}
            action_type = event.event_type

            if event.event_type == "tool_call":
                action_name = payload.get("name", "unknown_tool")
                action_args = payload.get("args", {})
            elif event.event_type in ["click", "input"]:
                action_args = payload
            elif event.source == "mobile":
                # Android mirror raw events: normalize into macro-executable
                # actions. touch_down/touch_up are gesture boundaries already
                # represented by the paired swipe/tap event — skip them.
                normalized = self._normalize_mobile_event(event.event_type, payload)
                if normalized is None:
                    return None
                action_name, action_args = normalized
                action_type = action_name

            # Determine category
            category = self._categorize_action(event.event_type, action_name)

            # Build UI context if available
            ui_context = None
            if event.screenshot_path or event.target_selector or event.target_text:
                ui_context = UIContext(
                    screenshot_path=event.screenshot_path,
                    element_selector=event.target_selector,
                    element_text=event.target_text,
                )

            state_context = dict(event.state_snapshot or {})
            if event.app_name:
                state_context.setdefault("app_name", event.app_name)
            if event.source:
                state_context.setdefault("source", event.source)

            return TraceStep(
                step_number=event.step_number,
                source=source,
                category=category,
                action_type=action_type,
                action_name=action_name,
                action_args=action_args,
                node_name=event.node_name,
                state_context=state_context,
                ui_context=ui_context,
                user_feedback=event.user_feedback,
            )

        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
            logger.error(f"Failed to parse event {event.id}: {e}")
            return None

    @staticmethod
    def _normalize_mobile_event(event_type: str, payload: dict) -> tuple[str, dict] | None:
        """Normalize raw Android mirror events into macro actions.

        Returns (action_name, action_args) or None to drop the event.
        The recorder emits touch_down/touch_up boundaries plus a composed
        swipe event per gesture; a near-zero-distance swipe is a tap.
        Mirror-window clicks arrive as mouse_click with device-pixel
        coordinates (transformed client-side in GlobalRecorderManager).
        """
        if event_type in ("touch_down", "touch_up"):
            return None
        if event_type == "mouse_click":
            # Mirror-window click: position already holds device pixels
            pos = payload.get("position") or {}
            if isinstance(pos, (list, tuple)) and len(pos) == 2:
                return ("tap", {"x": pos[0], "y": pos[1]})
            args = {k: v for k, v in {"x": payload.get("x"), "y": payload.get("y")}.items() if v is not None}
            return ("tap", args)
        if event_type == "swipe":
            x, y = payload.get("x"), payload.get("y")
            end_x = payload.get("swipe_end_x")
            end_y = payload.get("swipe_end_y")
            args = {k: v for k, v in {"x": x, "y": y}.items() if v is not None}
            if end_x is None or end_y is None or x is None or y is None:
                return ("tap", args)
            distance = ((end_x - x) ** 2 + (end_y - y) ** 2) ** 0.5
            if distance < 30:
                return ("tap", args)
            args["end_x"] = end_x
            args["end_y"] = end_y
            if payload.get("swipe_duration_ms") is not None:
                args["duration_ms"] = payload["swipe_duration_ms"]
            return ("swipe", args)
        if event_type == "key":
            # Mobile key executor reads payload["key"] / ["keycode"]
            return ("key_press", {"key": payload.get("key_code")})
        # region_extract and other annotated events pass through as-is
        return (event_type, payload)

    def _categorize_action(self, event_type: str, action_name: str) -> ActionCategory:
        """Determine the category of an action."""
        # Check tool-specific first
        if action_name in TOOL_CATEGORY_MAP:
            return TOOL_CATEGORY_MAP[action_name]

        # Fall back to action type
        return EVENT_CATEGORY_MAP.get(event_type, ActionCategory.OTHER)

    def to_narrative(self, sequence: TraceSequence) -> str:
        """
        Convert sequence to human-readable narrative for LLM synthesis.
        """
        try:
            from app.utils.template import render_template
            return render_template(
                "common/events/trace_narrative.prompt.j2",
                thread_id=sequence.thread_id,
                task_name=sequence.task_name,
                steps=sequence.steps,
                has_human_intervention=sequence.has_human_intervention
            )
        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
            logger.error(f"Failed to render Trace narrative: {e}")
            return f"Trace Narrative for {sequence.thread_id} (Error rendering template)"
