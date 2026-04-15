import json
import logging
import os
import time
from datetime import datetime
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult
from pydantic import Field

from app.core.config import settings
from app.core.context.manager import ContextManager
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.path import ensure_dir

logger = logging.getLogger(__name__)


class TraceParameters(DynamicBaseModel):
    """Dynamic parameters for a recorded action."""


class TraceContext(DynamicBaseModel):
    """Dynamic context (view hierarchy, URL, etc.) for a recorded action."""


class ActionTrace(DynamicBaseModel):
    """Represents a single user action captured during demonstration."""
    timestamp: float
    action_type: str  # click, type, swipe, key, navigate, etc.
    platform: str     # android, web, desktop
    parameters: TraceParameters
    context: TraceContext = Field(default_factory=TraceContext) # View hierarchy, URL, etc.
    screenshot_path: str | None = None


class TraceRecorder:
    """
    Captures user interaction traces from Mirror Sessions or Browsers.
    These traces are the raw material for Imitation Learning.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.traces: list[ActionTrace] = []
        self.is_recording = False
        self.output_dir = os.path.join(settings.BROWSER_ARTIFACTS_DIR, "traces", session_id)
        ensure_dir(self.output_dir)

    def start(self):
        """Starts the recording session."""
        logger.info(f"[TraceRecorder] Starting recording for session: {self.session_id}")
        self.is_recording = True
        self.traces = []

    def stop(self) -> str:
        """Stops recording and persists the trace to disk."""
        self.is_recording = False
        file_path = self._save_trace()
        logger.info(f"[TraceRecorder] Recording stopped. Trace saved to: {file_path}")
        return file_path

    async def record_action(
        self,
        action_type: str,
        platform: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
        screenshot_data: bytes | None = None
    ):
        """Records a single action with its context."""
        if not self.is_recording:
            return

        timestamp = time.time()
        screenshot_path = None

        if screenshot_data:
            screenshot_path = os.path.join(self.output_dir, f"step_{len(self.traces)}_{int(timestamp)}.png")
            with open(screenshot_path, "wb") as f:
                f.write(screenshot_data)

        trace = ActionTrace(
            timestamp=timestamp,
            action_type=action_type,
            platform=platform,
            parameters=parameters,
            context=context or {},
            screenshot_path=screenshot_path
        )
        self.traces.append(trace)
        logger.debug(f"[TraceRecorder] Action recorded: {action_type} on {platform}")

    def _save_trace(self) -> str:
        """Serializes the trace list to a JSON file."""
        trace_data = {
            "session_id": self.session_id,
            "recorded_at": datetime.now().isoformat(),
            "step_count": len(self.traces),
            "traces": [
                {
                    "timestamp": t.timestamp,
                    "action_type": t.action_type,
                    "platform": t.platform,
                    "parameters": t.parameters,
                    "context": t.context,
                    "screenshot_path": t.screenshot_path
                } for t in self.traces
            ]
        }

        file_path = os.path.join(self.output_dir, "trace.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(trace_data, f, indent=2, ensure_ascii=False)

        return file_path


# Global registry for active recorders
_active_recorders: dict[str, TraceRecorder] = {}


def get_recorder(session_id: str) -> TraceRecorder:
    if session_id not in _active_recorders:
        _active_recorders[session_id] = TraceRecorder(session_id)
    return _active_recorders[session_id]


# ---------------------------------------------------------------------------
# LangChain Callback Handler — persists agent actions into TraceEvent table
# ---------------------------------------------------------------------------


class TraceCallbackHandler(AsyncCallbackHandler):
    """
    LangChain callback that records every tool call and LLM output into
    the `TraceEvent` database table for imitation learning.

    Attached automatically by AgentEngine._setup_callbacks() for every
    agent node execution.
    """

    def __init__(self, thread_id: str):
        super().__init__()
        self.thread_id = thread_id
        self._step = 0

    # ------------------------------------------------------------------
    # Public LangChain callbacks
    # ------------------------------------------------------------------

    async def on_tool_start(self, serialized: dict, input_str: str, **kwargs) -> None:
        """Called when a tool starts execution."""
        tool_name = serialized.get("name", "unknown_tool")
        try:
            args = json.loads(input_str)
        except (json.JSONDecodeError, TypeError):
            args = {"raw": input_str}

        await self._save_event(
            action_type="tool_call",
            payload={"name": tool_name, "args": args},
        )

    async def on_tool_end(self, output: Any, *, name: str = "unknown_tool", **kwargs) -> None:
        """Called when a tool finishes execution."""
        # Robustly serialize any output type
        try:
            if isinstance(output, str):
                output_str = output
            elif output is None:
                output_str = "null"
            elif output is None:
                output_str = "null"
            elif isinstance(output, (dict, list)):
                output_str = json.dumps(output, default=str)
            else:
                try:
                    output_str = json.dumps(output, default=str)
                except (TypeError, ValueError):
                    output_str = str(output)
        except Exception:
            output_str = str(output)

        # Truncate long outputs
        if len(output_str) > 2000:
            output_str = output_str[:2000]

        await self._save_event(
            action_type="tool_result",
            payload={"name": name, "output": output_str, "success": True},
        )

    async def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        """Called when an LLM generates a response."""
        if not response.generations:
            return
        try:
            text = response.generations[0][0].text
            await self._save_event(
                action_type="llm_output",
                payload={"content": text},
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _save_event(self, action_type: str, payload: dict) -> None:
        """Persist a single trace event into the TraceEvent table."""
        try:
            from app.infrastructure.database.sql.database import session_scope
            from app.models.learning import (
                TraceEvent,  # avoid circular import at module load
            )

            self._step += 1
            ctx = ContextManager.current()
            state_snapshot = self._sanitize_snapshot(payload)

            async with session_scope() as session:
                event = TraceEvent(
                    thread_id=self.thread_id,
                    step_number=self._step,
                    action_type=action_type,
                    action_payload=json.dumps(payload, default=str),
                    state_snapshot=json.dumps(state_snapshot, default=str),
                    node_name=ctx.request_id if ctx else "unknown",
                    source="agent",
                    is_human_action=False,
                )
                session.add(event)
        except Exception as e:
            logger.debug(f"[TraceCallbackHandler] Failed to save event: {e}")

    def _sanitize_snapshot(self, state: Any) -> dict:
        """Safely convert arbitrary state into a JSON-serializable dict."""
        if isinstance(state, dict):
            # Strip heavy/sensitive fields
            return {k: v for k, v in state.items() if k not in ("environment_block",)}
        if hasattr(state, "dict"):
            return state.model_dump()
        return {"raw_state_type": type(state).__name__, "raw_state_value": str(state)}


# ---------------------------------------------------------------------------
# Episode Sync — reads TraceEvent rows and records episode to memory graph
# ---------------------------------------------------------------------------


async def sync_thread_to_graph(
    thread_id: str,
    project_id: int,
    goal: str,
    result_summary: str | None = None,
    concept_names: list[str] | None = None,
    source_message_id: str | None = None,
) -> None:
    """
    Syncs a completed thread's trace events into the long-term memory Episode graph.

    Reads all TraceEvent rows for the given thread_id, builds an episode
    summary, and records it via memory_manager.long_term.record_episode().
    Called by the Celery task ``engine_record_episode`` in tasks.py.

    Args:
        thread_id: The thread whose trace events to sync.
        project_id: Project context for the episode.
        goal: The high-level goal the agent was trying to achieve.
        result_summary: Optional short summary of the outcome.
        concept_names: Optional list of concept names the agent referenced.
        source_message_id: Optional originating message ID for traceability.
    """
    try:
        from sqlalchemy import select

        from app.models.learning import TraceEvent

        async with session_scope() as session:
            stmt = select(TraceEvent).where(TraceEvent.thread_id == thread_id).order_by(TraceEvent.step_number)
            result = await session.execute(stmt)
            events = result.scalars().all()

        if not events:
            logger.info(f"No trace events for thread '{thread_id}'. Skipping.")
            return

        # Build a compact action summary from the recorded events using template
        from app.utils import render_template

        action_data = []
        for ev in events[:50]:  # cap at 50 events
            try:
                payload = ev.action_payload if isinstance(ev.action_payload, dict) else json.loads(ev.action_payload) if ev.action_payload else {}
            except Exception:
                payload = {}

            action_info = {
                "type": ev.action_type,
                "name": payload.get('name', '?') if ev.action_type == "tool_call" else None,
                "args": json.dumps(payload.get('args', {})) if ev.action_type == "tool_call" else None,
                "output": payload.get("output") if ev.action_type == "tool_result" else None,
                "content": payload.get("content") if ev.action_type == "llm_output" else None,
            }
            action_data.append(action_info)

        actions_text = render_template("common/events/action_summary.prompt.j2", actions=action_data)

        # Improved result summary fallback
        has_real_result = result_summary and result_summary != "unknown"
        episode_result = result_summary if has_real_result else (
            f"Finished session with {len(events)} steps for task: {goal}"
        )

        from app.core.memory.interfaces.long_term import Episode

        episode = Episode(
            goal=goal,
            result=episode_result,
            plan_summary=actions_text,
            error_msg=None,
            project_id=project_id,
            source_message_id=source_message_id,
        )

        from app.core.memory.lifespan import MemoryLifespanManager
        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        manager = container.memory_manager
        episode_id = await manager.long_term.record_episode(episode)

        # Link episode to concepts if provided
        if episode_id and concept_names:
            await manager.long_term.link_episode_to_concepts(
                episode_id=episode_id,
                concept_names=concept_names,
                project_id=project_id,
            )

        logger.info(f"Episode recorded for thread '{thread_id}' ({len(events)} events, id={episode_id})")

    except Exception as e:
        logger.error(f"Failed to sync thread '{thread_id}': {e}")
