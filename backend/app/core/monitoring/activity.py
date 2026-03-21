"""
Activity Monitor for tracking agent execution state.

Provides real-time state management and event publishing for agent runs.
Uses ActivityStateService for state persistence and Cache for Pub/Sub.
"""

import json
import logging
import time
from typing import Any

from app.infrastructure.cache import cache
from app.models.schemas.events import (
    AgentStateEvent,
    ArtifactEvent,
    HumanRequestEvent,
    StatusEvent,
    StepEvent,
)
from app.services.cache_services import ActivityStateService

logger = logging.getLogger(__name__)


class ActivityMonitor:
    """
    Monitors and manages agent activity state.
    
    Provides high-level operations for tracking run state, steps, artifacts,
    and human interaction requests. Events are published via Pub/Sub for
    real-time UI updates.
    """

    _instance = None

    def __init__(self):
        self._state_service = ActivityStateService(cache)

    @property
    def client(self):
        """Legacy compatibility for cache access."""
        return cache

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start_run(self, thread_id: str, main_goal: str = "处理用户请求"):
        """Initialize activity state for a new run."""
        await self._state_service.start_run(thread_id, main_goal)

    async def end_run(self, thread_id: str, status="done", final_outcome: str = None):
        """Mark run as ended and publish status change."""
        result = await self._state_service.end_run(thread_id, status, final_outcome)
        
        # Publish final status
        await cache.publish(
            f"chat:{thread_id}:events",
            StatusEvent(status=result.get("status", status)).model_dump_json()
        )
        
        return result

    async def stop_run(self, thread_id: str):
        """Signal a run to stop."""
        await self._state_service.signal_stop(thread_id)

    async def check_cancellation(self, thread_id: str):
        """Check if run is marked for stopping and raise exception if so."""
        from app.core.exceptions import AgentCancelledException

        if await self._state_service.check_cancellation(thread_id):
            raise AgentCancelledException(f"Run {thread_id} cancelled by user")

    async def set_interrupted(
        self, thread_id: str, reason: str = "awaiting_human_input"
    ):
        """Mark a run as interrupted (paused for human input)."""
        await self._state_service.set_interrupted(thread_id, reason)

    async def set_human_request(self, thread_id: str, request_data: dict[str, Any]):
        """
        Store a structured Human Request (HITL).
        Replaces simple 'set_interrupted' for rich interactions.
        """
        success = await self._state_service.set_human_request(thread_id, request_data)
        
        if success:
            # Publish Event
            await cache.publish(
                f"chat:{thread_id}:events",
                HumanRequestEvent(action="create", data=request_data).model_dump_json(),
            )

            # [HITL FIX] Also publish StatusEvent so UI knows we are interrupted
            await cache.publish(
                f"chat:{thread_id}:events", 
                StatusEvent(status="interrupted").model_dump_json()
            )

    async def clear_human_request(self, thread_id: str):
        """Clear human request upon resumption."""
        success = await self._state_service.clear_human_request(thread_id)
        
        if success:
            # Publish Event
            await cache.publish(
                f"chat:{thread_id}:events",
                HumanRequestEvent(action="clear", data={}).model_dump_json(),
            )

    async def request_human_interaction(
        self,
        thread_id: str,
        request_type: str,
        prompt: str,
        payload: dict[str, Any] | None = None,
        allow_cancel: bool = True
    ) -> None:
        """
        Request interaction from human user and PAUSE agent execution.

        This unifies HITL and UI actions into a single interface.
        The agent will be in 'interrupted' state until user responds.

        Args:
            thread_id: The thread ID
            request_type: Type of interaction (e.g., "text_input", "project_switch", "confirm")
            prompt: Message shown to user explaining what's needed
            payload: Additional data for the interaction (type-specific)
            allow_cancel: Whether user can cancel this request
        """
        from app.core.monitoring.ui_actions import HumanRequestType

        # Validate request type
        valid_types = [t.value for t in HumanRequestType]
        if request_type not in valid_types:
            logger.warning(f"[ActivityMonitor] Unknown request type: {request_type}")

        # Store the request
        request_data = {
            "type": request_type,
            "prompt": prompt,
            "allow_cancel": allow_cancel,
            "payload": payload or {},
        }
        
        success = await self._state_service.set_human_request(thread_id, request_data)
        
        if success:
            # Publish Event
            await cache.publish(
                f"chat:{thread_id}:events",
                HumanRequestEvent(action="create", data=request_data).model_dump_json(),
            )

            # [HITL FIX] Also publish StatusEvent
            await cache.publish(
                f"chat:{thread_id}:events", 
                StatusEvent(status="interrupted").model_dump_json()
            )

            logger.info(f"[ActivityMonitor] Requested '{request_type}' interaction for thread {thread_id}")

    async def set_active_memory(self, thread_id: str, memory_id: str, memory_name: str):
        """Track which memory is currently being accessed by the Agent."""
        key = f"activity:{thread_id}"
        if not await cache.exists(key):
            return

        memories_json = await cache.hget(key, "active_memories")
        memories = json.loads(memories_json) if memories_json else []

        # Add if not already in list
        if not any(m.get("id") == memory_id for m in memories):
            memories.append({"id": memory_id, "name": memory_name})
            await cache.hset(
                key,
                mapping={
                    "active_memories": json.dumps(memories),
                    "updated_at": str(time.time()),
                },
            )

    async def clear_active_memories(self, thread_id: str):
        """Clear active memory highlights at end of run."""
        key = f"activity:{thread_id}"
        if await cache.exists(key):
            await cache.hset(key, "active_memories", json.dumps([]))

    async def add_step(
        self, thread_id: str, name: str, step_type="node", parent_id: int = None
    ):
        """Add a new step and return its ID."""
        step_id = await self._state_service.add_step(thread_id, name, step_type, parent_id)
        
        if step_id:
            # Publish Event
            await cache.publish(
                f"chat:{thread_id}:events",
                StepEvent(action="create", id=step_id, data={"name": name, "status": "running"}).model_dump_json(),
            )
        
        return step_id

    async def update_step(
        self, thread_id: str, step_id: int, status: str, details: str = None
    ):
        """Update step status and optionally details."""
        key = f"activity:{thread_id}"
        lock_key = f"lock:{key}"

        try:
            async with cache.lock(lock_key, timeout=2.0, blocking_timeout=1.0):
                steps_json = await cache.hget(key, "steps")
                if not steps_json:
                    return

                steps = json.loads(steps_json) if isinstance(steps_json, str) else steps_json
                modified = False

                for step in steps:
                    if step["id"] == step_id:
                        step["status"] = status
                        if details:
                            step["details"] = details
                        if status in ["done", "failed"]:
                            duration = time.time() - step["start_time"]
                            step["time"] = f"{duration:.2f}s"
                        modified = True
                        break

                if modified:
                    await cache.hset(
                        key,
                        mapping={"steps": json.dumps(steps), "updated_at": str(time.time())},
                    )

                    # Publish Event
                    update_data = {"status": status}
                    if details:
                        update_data["details"] = details
                    await cache.publish(
                        f"chat:{thread_id}:events",
                        StepEvent(action="update", id=step_id, data=update_data).model_dump_json(),
                    )
        except Exception:
            pass

    async def update_agent_state(
        self, thread_id: str, mode: str, task_name: str, task_status: str, details: dict[str, Any] = None
    ):
        """Update agent state and publish event."""
        state = {
            "mode": mode,
            "task_name": task_name,
            "task_status": task_status,
        }
        if details:
            state["details"] = details

        await self._state_service.update_agent_state(thread_id, state)

        # Publish Event
        await cache.publish(
            f"chat:{thread_id}:events", 
            AgentStateEvent(data=state).model_dump_json()
        )

    async def log_event(self, event_type: str, data: dict[str, Any], thread_id: str = "system"):
        """Generic event logger for system and session events."""
        timestamp = time.time()
        payload = {
            "type": event_type,
            "data": data,
            "timestamp": timestamp
        }
        
        # Log to a system list in cache for persistence
        await cache.lpush(f"system:logs:{event_type}", json.dumps(payload))
        await cache.ltrim(f"system:logs:{event_type}", 0, 99)  # Keep last 100
        
        # Publish to the chat stream if it's a session event
        if thread_id != "system":
            await cache.publish(
                f"chat:{thread_id}:events",
                json.dumps({"event": "system_log", "data": payload})
            )
        
        logger.info(f"[ActivityMonitor] Event logged: {event_type}")

    async def add_artifact(
        self,
        thread_id: str,
        name: str,
        artifact_type: str,
        status="created",
        path: str = None,
    ):
        """Add or update an artifact and publish event."""
        await self._state_service.add_artifact(thread_id, name, artifact_type, status, path)
        
        # Get the artifact we just added
        activity = await self._state_service.get_state(thread_id)
        artifacts = activity.get("artifacts", [])
        target_art = next((a for a in artifacts if a["name"] == name), None)
        
        if target_art:
            action = "update" if status == "modified" else "create"
            await cache.publish(
                f"chat:{thread_id}:events",
                ArtifactEvent(action=action, name=name, data=target_art).model_dump_json(),
            )

    async def get_activity(self, thread_id: str):
        """Get full activity state for a thread."""
        return await self._state_service.get_state(thread_id)

    async def get_statuses(self, thread_ids: list[str]) -> dict[str, str]:
        """Batch fetch statuses for multiple threads efficiently."""
        if not thread_ids:
            return {}

        pipeline = cache.pipeline()
        for tid in thread_ids:
            pipeline.hget(f"activity:{tid}", "status")

        results = await pipeline.execute()

        status_map = {}
        for i, status in enumerate(results):
            status_map[thread_ids[i]] = status if status else "unknown"

        return status_map


# Global Instance
activity_monitor = ActivityMonitor.get_instance()
