"""
Activity Monitor for tracking agent execution state.

Provides real-time state management and event publishing for agent runs.
Uses ActivityStateService for state persistence and Cache for Pub/Sub.
"""

import json
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from app.core.events import system_bus
from app.core.events.schemas import SystemLogEvent, SystemStatusEvent
from app.core.monitoring.schemas import (
    AgentActivityState,
    HumanRequestData,
    SystemLogPayload,
)
from app.infrastructure.cache import cache
from app.models.schemas.events import (
    AgentStateEvent,
    ArtifactEvent,
    HumanRequestEvent,
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

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @asynccontextmanager
    async def run_scope(self, thread_id: str, main_goal: str = "处理用户请求") -> AsyncGenerator[str, None]:
        """
        Unified Agent Lifecycle Context Manager.

        Handles:
        - start_run / end_run
        - run_id generation and context injection
        - Early cancellation check
        - Global exception handling and status reporting

        Yields:
            run_id (str): The unique ID for this execution attempt.
        """
        from app.core.context.manager import ContextManager
        from app.core.exceptions import (
            AgentCancelledException,
            AgentHumanInterruptException,
        )
        from app.utils.id import gen_uuid

        run_id = f"run-{gen_uuid()[:8]}"

        # 1. Start Run
        await self.start_run(thread_id, main_goal, run_id=run_id)
        logger.info(f"[ActivityMonitor] 🚀 Starting lifecycle for thread {thread_id} (Run: {run_id})")

        # 2. Sync Metadata to Context
        ctx = ContextManager.current()
        if ctx and ctx.thread_id == thread_id:
            ctx.run_id = run_id

        try:
            # 3. Pre-run cancellation check
            await self.check_cancellation(thread_id)

            yield run_id

            # 4. Success End
            await self.end_run(thread_id, status="done", run_id=run_id)

        except AgentCancelledException:
            logger.info(f"[ActivityMonitor] 🛑 Run {run_id} cancelled by user")
            await self.end_run(thread_id, status="cancelled", run_id=run_id)
            raise  # Re-raise for upper layers if needed (BackgroundAgent handles it)

        except AgentHumanInterruptException:
            logger.info(f"[ActivityMonitor] ⏸️ Run {run_id} interrupted for human input")
            # status "interrupted" is handled by set_human_request usually,
            # but we keep end_run call if appropriate
            raise

        except Exception as e:
            logger.error(f"[ActivityMonitor] ❌ Run {run_id} failed with error: {e}", exc_info=True)
            await self.end_run(thread_id, status="failed", run_id=run_id)
            raise

    async def start_run(self, thread_id: str, main_goal: str = "处理用户请求", run_id: str = None):
        """Initialize activity state for a new run."""
        await self._state_service.start_run(thread_id, main_goal)

        # Publish internal AgentSessionStartedEvent (automated bridge will handle UI RunStartEvent)
        from app.core.engine.event.publishers import publish_agent_session_started
        await publish_agent_session_started(thread_id=thread_id)

    async def end_run(self, thread_id: str, status="done", final_outcome: str = None, run_id: str = None):
        """Mark run as ended and publish status change."""
        result = await self._state_service.end_run(thread_id, status, final_outcome)

        # 1. Publish internal AgentRunCompletedEvent (automated bridge handles UI RunEndEvent)
        from app.core.engine.event.publishers import publish_agent_run_completed
        await publish_agent_run_completed(
            thread_id=thread_id,
            status=status,
            payload={"run_id": run_id, "outcome": final_outcome}
        )

        # 2. Publish internal SystemStatusEvent (automated bridge handles UI StatusEvent)
        await system_bus.publish(SystemStatusEvent(thread_id=thread_id, status=result.get("status", status)))

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

    async def set_human_request(self, thread_id: str, request_data: HumanRequestData):
        """
        Store a structured Human Request (HITL).
        Replaces simple 'set_interrupted' for rich interactions.
        """
        request_dict = request_data.model_dump() if isinstance(request_data, HumanRequestData) else request_data
        success = await self._state_service.set_human_request(thread_id, request_dict)

        if success:
            # Publish internal Event (automated bridge will handle UI)
            await system_bus.publish(
                HumanRequestEvent(
                    thread_id=thread_id,
                    action="create",
                    prompt=request_dict.get("prompt"),
                    request_type=request_dict.get("type"),
                    allow_cancel=request_dict.get("allow_cancel", True),
                    payload=request_dict.get("payload", {})
                )
            )

            # [HITL FIX] Also publish internal SystemStatusEvent
            await system_bus.publish(SystemStatusEvent(thread_id=thread_id, status="interrupted"))

    async def clear_human_request(self, thread_id: str):
        """Clear human request upon resumption."""
        success = await self._state_service.clear_human_request(thread_id)

        if success:
            # Publish internal Events
            await system_bus.publish(HumanRequestEvent(thread_id=thread_id, action="clear"))
            await system_bus.publish(SystemStatusEvent(thread_id=thread_id, status="idle"))

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
        request_data = HumanRequestData(
            type=request_type,
            prompt=prompt,
            allow_cancel=allow_cancel,
            payload=payload or {},
        )

        success = await self._state_service.set_human_request(thread_id, request_data.model_dump())

        if success:
            # Publish internal Events (automated bridge will handle UI)
            await system_bus.publish(
                HumanRequestEvent(
                    thread_id=thread_id,
                    action="create",
                    prompt=request_data.prompt,
                    request_type=request_data.type,
                    allow_cancel=request_data.allow_cancel,
                    payload=request_data.payload
                )
            )

            # [HITL FIX] Also publish internal SystemStatusEvent
            await system_bus.publish(SystemStatusEvent(thread_id=thread_id, status="interrupted"))

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

    async def update_agent_state(
        self, thread_id: str, mode: str, task_name: str, task_status: str, details: dict[str, Any] | None = None
    ):
        """Update agent state and publish event."""
        state = AgentActivityState(
            mode=mode,
            task_name=task_name,
            task_status=task_status,
            details=details or {}
        )

        await self._state_service.update_agent_state(thread_id, state.model_dump())

        # Publish internal Event
        await system_bus.publish(
            AgentStateEvent(
                thread_id=thread_id,
                mode=mode,
                task_name=task_name,
                task_status=task_status
            )
        )

    async def log_event(self, event_type: str, data: dict[str, Any], thread_id: str = "system"):
        """Generic event logger for system and session events."""
        timestamp = time.time()
        payload = SystemLogPayload(
            type=event_type,
            data=data,
            timestamp=timestamp
        )

        # Log to a system list in cache for persistence
        # Use pipeline to make lpush+ltrim atomic
        pipe = cache.pipeline()
        pipe.lpush(f"system:logs:{event_type}", payload.model_dump_json())
        pipe.ltrim(f"system:logs:{event_type}", 0, 99)  # Keep last 100
        await pipe.execute()

        # Publish to the chat stream if it's a session event
        if thread_id != "system":
            await system_bus.publish(
                SystemLogEvent(
                    thread_id=thread_id,
                    log_type=event_type,
                    log_data=data
                )
            )

        logger.info(f"[ActivityMonitor] Event logged: {event_type} (Thread: {thread_id})")

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
            await system_bus.publish(
                ArtifactEvent(
                    thread_id=thread_id,
                    id=target_art.get("id", ""),
                    name=target_art.get("name", ""),
                    kind=target_art.get("kind", ""),
                    status=target_art.get("status", "pending"),
                    path=target_art.get("path")
                )
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
