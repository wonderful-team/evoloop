import json
import logging
import os
import time
from datetime import datetime
from typing import Any

from app.core.config import settings
from app.core.file import ensure_dir
from app.core.learning.schemas import ActionTrace

logger = logging.getLogger(__name__)


class TraceRecorder:
    """
    Captures user interaction traces from Mirror Sessions or Browsers.
    These traces are the raw material for Imitation Learning.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.traces: list[ActionTrace] = []
        self.is_recording = False
        self.output_dir = os.path.join(
            settings.BROWSER_ARTIFACTS_DIR, "traces", session_id
        )
        ensure_dir(self.output_dir)

    def start(self):
        """Starts the recording session."""
        logger.info(
            f"[TraceRecorder] Starting recording for session: {self.session_id}"
        )
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
        screenshot_data: bytes | None = None,
    ):
        """Records a single action with its context."""
        if not self.is_recording:
            return

        timestamp = time.time()
        screenshot_path = None

        if screenshot_data:
            screenshot_path = os.path.join(
                self.output_dir, f"step_{len(self.traces)}_{int(timestamp)}.png"
            )
            with open(screenshot_path, "wb") as f:
                f.write(screenshot_data)

        trace = ActionTrace(
            timestamp=timestamp,
            action_type=action_type,
            platform=platform,
            parameters=parameters,
            context=context or {},
            screenshot_path=screenshot_path,
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
                    "parameters": t.parameters.model_dump(),
                    "context": t.context.model_dump(),
                    "screenshot_path": t.screenshot_path,
                }
                for t in self.traces
            ],
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
# Episode Sync — reads TraceEvent rows and records episode to memory graph
# ---------------------------------------------------------------------------


async def sync_thread_to_graph(
    thread_id: str,
    project_id: int,
    goal: str,
    result_summary: str | None = None,
    source_message_id: str | None = None,
) -> None:
    """
    Syncs a completed thread's trace events into the long-term memory Episode graph.

    Reads TraceEvent rows to determine success, then records a concise episode
    via memory_manager.record_episode().
    """
    try:
        from app.core.learning.trace.repository import trace_repository

        events = await trace_repository.get_by_thread(thread_id)

        if not events:
            logger.info(f"No trace events for thread '{thread_id}'. Skipping.")
            return

        # Improved result summary fallback (Outcome)
        has_real_result = result_summary and result_summary != "unknown"
        episode_result = (
            result_summary
            if has_real_result
            else (f"Finished session with {len(events)} steps.")
        )

        from app.core.memory.lifespan import MemoryLifespanManager

        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        manager = container.memory_manager

        from app.core.memory.schemas import Episode

        # Unified recording: Create Episode object first
        episode_obj = Episode(
            goal=goal,
            result=episode_result,
            project_id=project_id,
            source_message_id=source_message_id,
            plan_summary="",  # Optional
        )

        episode_id = await manager.record_episode(episode_obj)

        logger.info(f"Episode recorded for thread '{thread_id}' (id={episode_id})")

    except Exception as e:
        logger.exception(f"Failed to sync thread '{thread_id}': {e}")
