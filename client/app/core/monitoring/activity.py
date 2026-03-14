"""
Activity Monitor for Sidecar Mode.

Replaces Redis-based ActivityMonitor with a lightweight local tracker
that sends events via Sidecar protocol to Tauri.

Note: In Sidecar architecture, activity state is maintained by Tauri/Server,
not by the Client. Client only sends events.
"""

import json
import logging
import time
from typing import Any

from app.models.schemas.events import (
    AgentStateEvent,
    ArtifactEvent,
    HumanRequestEvent,
    StatusEvent,
    StepEvent,
)
from app.sidecar.handlers.events import events

logger = logging.getLogger(__name__)


class ActivityMonitor:
    """
    Lightweight activity tracker for Sidecar mode.
    Sends events to Tauri via Sidecar protocol instead of storing in Redis.
    """

    _instance = None

    def __init__(self):
        self._local_steps: dict[str, list[dict]] = {}
        self._local_artifacts: dict[str, list[dict]] = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start_run(self, thread_id: str, main_goal: str = "处理用户请求"):
        """Notify Tauri that a run has started."""
        logger.info(f"[ActivityMonitor] Run started: {thread_id}")
        await events._send("run_started", {
            "thread_id": thread_id,
            "main_goal": main_goal,
            "status": "running",
            "timestamp": time.time(),
        })

        # Initialize local tracking
        self._local_steps[thread_id] = []
        self._local_artifacts[thread_id] = []

    async def end_run(self, thread_id: str, status="done"):
        """Notify Tauri that a run has ended."""
        logger.info(f"[ActivityMonitor] Run ended: {thread_id} with status {status}")

        # Mark remaining running steps as done/cancelled
        if thread_id in self._local_steps:
            for step in self._local_steps[thread_id]:
                if step["status"] == "running":
                    step["status"] = "cancelled" if status == "cancelled" else "done"
                    await events.step_update(
                        thread_id=thread_id,
                        step_id=step["id"],
                        status=step["status"]
                    )

        await events._send("run_ended", {
            "thread_id": thread_id,
            "status": status,
            "timestamp": time.time(),
        })

        # Cleanup local tracking
        self._local_steps.pop(thread_id, None)
        self._local_artifacts.pop(thread_id, None)

    async def stop_run(self, thread_id: str):
        """Signal a run to stop (will be checked on next step)."""
        await events._send("run_stopping", {
            "thread_id": thread_id,
            "timestamp": time.time(),
        })

    async def check_cancellation(self, thread_id: str):
        """Check if run should be cancelled.

        In Sidecar mode, this should be checked via Tauri polling or events.
        For now, we rely on the execution layer to handle cancellation signals.
        """
        # TODO: Implement cancellation check via Tauri polling or shared state
        pass

    async def set_interrupted(
        self, thread_id: str, reason: str = "awaiting_human_input"
    ):
        """Mark a run as interrupted (paused for human input)."""
        await events._send("run_interrupted", {
            "thread_id": thread_id,
            "reason": reason,
            "timestamp": time.time(),
        })

    async def set_human_request(self, thread_id: str, request_data: dict[str, Any]):
        """Store a structured Human Request (HITL)."""
        await events._send("human_request", {
            "thread_id": thread_id,
            "action": "create",
            "data": request_data,
            "timestamp": time.time(),
        })

    async def clear_human_request(self, thread_id: str):
        """Clear human request upon resumption."""
        await events._send("human_request", {
            "thread_id": thread_id,
            "action": "clear",
            "timestamp": time.time(),
        })

    async def request_human_interaction(
        self,
        thread_id: str,
        request_type: str,
        prompt: str,
        payload: dict[str, Any] | None = None,
        allow_cancel: bool = True
    ) -> None:
        """Request interaction from human user and PAUSE agent execution."""
        from app.core.monitoring.ui_actions import HumanRequestType

        # Validate request type
        valid_types = [t.value for t in HumanRequestType]
        if request_type not in valid_types:
            logger.warning(f"[ActivityMonitor] Unknown request type: {request_type}")

        request_data = {
            "type": request_type,
            "prompt": prompt,
            "allow_cancel": allow_cancel,
            "payload": payload or {},
        }

        await events._send("human_request", {
            "thread_id": thread_id,
            "action": "create",
            "data": request_data,
            "timestamp": time.time(),
        })

        logger.info(f"[ActivityMonitor] Requested '{request_type}' interaction for thread {thread_id}")

    async def set_active_memory(self, thread_id: str, memory_id: str, memory_name: str):
        """Track which memory is currently being accessed by the Agent."""
        await events._send("active_memory", {
            "thread_id": thread_id,
            "action": "set",
            "memory_id": memory_id,
            "memory_name": memory_name,
            "timestamp": time.time(),
        })

    async def clear_active_memories(self, thread_id: str):
        """Clear active memory highlights at end of run."""
        await events._send("active_memory", {
            "thread_id": thread_id,
            "action": "clear",
            "timestamp": time.time(),
        })

    async def add_step(
        self, thread_id: str, name: str, step_type="node", parent_id: int = None
    ):
        """Add a step and notify Tauri."""
        if thread_id not in self._local_steps:
            self._local_steps[thread_id] = []

        step_id = len(self._local_steps[thread_id]) + 1
        new_step = {
            "id": step_id,
            "name": name,
            "status": "running",
            "type": step_type,
            "parent_id": parent_id,
            "start_time": time.time(),
            "time": "0s",
        }
        self._local_steps[thread_id].append(new_step)

        await events.step_create(
            thread_id=thread_id,
            step_id=step_id,
            name=name,
            step_type=step_type
        )

        return step_id

    async def update_step(
        self, thread_id: str, step_id: int, status: str, details: str = None
    ):
        """Update a step and notify Tauri."""
        if thread_id not in self._local_steps:
            return

        for step in self._local_steps[thread_id]:
            if step["id"] == step_id:
                step["status"] = status
                if details:
                    step["details"] = details
                if status in ["done", "failed"]:
                    duration = time.time() - step.get("start_time", time.time())
                    step["time"] = f"{duration:.2f}s"
                break

        await events.step_update(
            thread_id=thread_id,
            step_id=step_id,
            status=status,
            details=details
        )

    async def update_agent_state(
        self, thread_id: str, mode: str, task_name: str, task_status: str, details: dict[str, Any] = None
    ):
        """Update agent state and notify Tauri."""
        state = {
            "mode": mode,
            "task_name": task_name,
            "task_status": task_status,
        }
        if details:
            state["details"] = details

        await events._send("agent_state", {
            "thread_id": thread_id,
            "data": state,
            "timestamp": time.time(),
        })

    async def log_event(self, event_type: str, data: dict[str, Any], thread_id: str = "system"):
        """Generic event logger for system and session events."""
        await events._send("system_log", {
            "thread_id": thread_id,
            "event_type": event_type,
            "data": data,
            "timestamp": time.time(),
        })
        logger.info(f"[ActivityMonitor] Event logged: {event_type}")

    async def add_artifact(
        self,
        thread_id: str,
        name: str,
        artifact_type: str,
        status="created",
        path: str = None,
    ):
        """Add an artifact and notify Tauri."""
        if thread_id not in self._local_artifacts:
            self._local_artifacts[thread_id] = []

        # Check if exists
        for art in self._local_artifacts[thread_id]:
            if art["name"] == name:
                art["status"] = "modified"
                await events._send("artifact", {
                    "thread_id": thread_id,
                    "action": "update",
                    "name": name,
                    "data": art,
                })
                return

        artifact = {
            "id": len(self._local_artifacts[thread_id]) + 1,
            "name": name,
            "type": artifact_type,
            "status": status,
            "path": path,
            "icon": "FileCode",
        }
        self._local_artifacts[thread_id].append(artifact)

        await events._send("artifact", {
            "thread_id": thread_id,
            "action": "create",
            "name": name,
            "data": artifact,
        })

    async def get_activity(self, thread_id: str) -> dict:
        """Get local activity state (for compatibility)."""
        steps = self._local_steps.get(thread_id, [])
        artifacts = self._local_artifacts.get(thread_id, [])

        return {
            "status": "running" if steps else "idle",
            "main_goal": "",
            "updated_at": time.time(),
            "steps": steps,
            "artifacts": artifacts,
            "agent_state": {},
            "verification": {},
            "active_memories": [],
            "human_request": None,
        }

    async def get_statuses(self, thread_ids: list[str]) -> dict[str, str]:
        """Batch fetch statuses for multiple threads (local only)."""
        status_map = {}
        for tid in thread_ids:
            steps = self._local_steps.get(tid, [])
            status_map[tid] = "running" if steps else "unknown"
        return status_map


# Global Instance
activity_monitor = ActivityMonitor.get_instance()
