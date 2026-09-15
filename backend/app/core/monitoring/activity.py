"""
Activity Monitor for tracking agent execution state.

Provides real-time state management and event publishing for agent runs.
Uses ActivityStateService for state persistence and Cache for Pub/Sub.
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.events import system_bus
from app.core.hitl.types import HumanRequestType
from app.core.monitoring.constants import ActivityStatus
from app.core.monitoring.event import SystemLogEvent, SystemStatusEvent
from app.core.monitoring.schemas import (
    AgentActivityState,
    HumanRequestData,
    SystemLogPayload,
)

if TYPE_CHECKING:
    from app.core.execution.terminal.background.models import BackgroundTask
from app.core.monitoring.activity_state import ActivityStateService
from app.infrastructure.cache import cache
from app.infrastructure.database import session_scope
from app.models import AgentActivity
from app.models.schemas.events import (
    AgentStateEvent,
    ArtifactEvent,
    HumanRequestEvent,
)

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
    async def run_scope(
        self,
        thread_id: str,
        main_goal: str = "",
        task_type: str = None,
        project_id: int | None = None,
    ) -> AsyncGenerator[str, None]:
        from app.core.context.manager import ContextManager
        from app.core.exceptions import (
            AgentCancelledException,
            AgentHumanInterruptException,
        )
        from app.infrastructure.database import session_scope
        from app.utils.id import gen_uuid

        run_id = f"run-{gen_uuid()[:8]}"

        await self._state_service.start_run(thread_id, main_goal, run_id=run_id)
        logger.info(
            f"[ActivityMonitor] 🚀 Starting lifecycle for thread {thread_id} (Run: {run_id})"
        )
        await self._publish_session_started(thread_id, project_id)

        ctx = ContextManager.current()
        if ctx and ctx.thread_id == thread_id:
            ctx.run_id = run_id

        try:
            # Cancellation check before yield so that a stale stop signal does not
            # silently kill a new run without emitting a run_end event.
            async with session_scope() as session:
                await self.check_cancellation(thread_id, session=session)

            yield run_id

            # End phase: skip if monitoring subscriber already terminated
            async with session_scope() as session:
                activity = await session.get(AgentActivity, thread_id)
                if activity and activity.status in (
                    ActivityStatus.DONE,
                    ActivityStatus.FAILED,
                    ActivityStatus.CANCELLED,
                    ActivityStatus.QUOTA_EXHAUSTED,
                ):
                    logger.debug(
                        f"[ActivityMonitor] Skipping end_run for {thread_id}: already {activity.status}"
                    )
                else:
                    result = await self._state_service.end_run(
                        thread_id, ActivityStatus.DONE, run_id=run_id
                    )
                    await self._publish_run_completed(
                        thread_id, result, run_id, task_type
                    )

        except AgentCancelledException:
            # 用户主动取消是预期流程，非错误，不打印 Traceback。
            logger.info(f"[ActivityMonitor] 🛑 Run {run_id} cancelled by user")
            result = await self._state_service.end_run(
                thread_id, ActivityStatus.CANCELLED, run_id=run_id
            )
            await self._publish_run_completed(thread_id, result, run_id, task_type)
            raise

        except asyncio.CancelledError:
            logger.info(
                f"[ActivityMonitor] 🛑 Run {run_id} cancelled by task cancellation"
            )
            result = await self._state_service.end_run(
                thread_id, ActivityStatus.CANCELLED, run_id=run_id
            )
            await self._publish_run_completed(thread_id, result, run_id, task_type)
            raise

        except AgentHumanInterruptException:
            # HITL 挂起等人是合法状态（非失败）：落 HUMAN_INTERRUPT 终态并发布，
            # 否则 activity 悬挂 running、事件系统无感知（值守 reconcile 会误判死亡）。
            # 用户答复后 resume 链路重新 start_run，生命周期正常接续。
            logger.info(f"[ActivityMonitor] ⏸️ Run {run_id} interrupted for human input")
            result = await self._state_service.end_run(
                thread_id, ActivityStatus.HUMAN_INTERRUPT, run_id=run_id
            )
            await self._publish_run_completed(thread_id, result, run_id, task_type)
            raise

        except Exception as e:
            logger.exception(
                f"[ActivityMonitor] ❌ Run {run_id} failed with error: {e}"
            )
            result = await self._state_service.end_run(
                thread_id, ActivityStatus.FAILED, run_id=run_id
            )
            await self._publish_run_completed(thread_id, result, run_id, task_type)
            raise

    async def _publish_session_started(
        self, thread_id: str, project_id: int | None = None
    ):
        from app.core.engine.event.publishers import publish_agent_session_started

        await publish_agent_session_started(thread_id=thread_id, project_id=project_id)

    async def _publish_run_completed(
        self, thread_id: str, result, run_id: str, task_type: str | None
    ):
        from app.core.engine.event.publishers import publish_agent_run_completed

        await publish_agent_run_completed(
            thread_id=thread_id,
            status=result.status,
            payload={
                "run_id": run_id,
                "task_type": task_type,
                "outcome": result.status,
            },
        )
        from app.core.events.publishers import system_bus
        from app.core.monitoring.event import SystemStatusEvent

        await system_bus.publish(
            SystemStatusEvent(thread_id=thread_id, status=result.status)
        )

    async def start_run(
        self,
        thread_id: str,
        main_goal: str = "",
        run_id: str = None,
        project_id: int | None = None,
    ):
        """Initialize activity state for a new run."""
        await self._state_service.start_run(thread_id, main_goal, run_id=run_id)

        # Publish internal AgentSessionStartedEvent (automated bridge will handle UI RunStartEvent)
        from app.core.engine.event.publishers import publish_agent_session_started

        await publish_agent_session_started(thread_id=thread_id, project_id=project_id)

    async def end_run(
        self,
        thread_id: str,
        status=ActivityStatus.DONE,
        final_outcome: str = None,
        run_id: str = None,
        task_type: str = None,
    ):
        """Mark run as ended and publish status change."""
        result = await self._state_service.end_run(
            thread_id, status, final_outcome, run_id=run_id
        )

        # 1. Publish internal AgentRunCompletedEvent (automated bridge handles UI RunEndEvent)
        from app.core.engine.event.publishers import publish_agent_run_completed

        await publish_agent_run_completed(
            thread_id=thread_id,
            status=result.status,
            payload={
                "run_id": run_id,
                "outcome": final_outcome,
                "task_type": task_type,
            },
        )

        # 2. Publish SystemStatusEvent (system_bus: Python subscribers + bridge → SSE)
        await system_bus.publish(
            SystemStatusEvent(thread_id=thread_id, status=result.status)
        )

        return result

    async def stop_run(self, thread_id: str):
        """Signal a run to stop."""
        await self._state_service.signal_stop(thread_id)

    async def check_cancellation(self, thread_id: str, session=None):
        """Check if run is marked for stopping and raise exception if so."""
        from app.core.exceptions import AgentCancelledException

        if await self._state_service.check_cancellation(thread_id, session=session):
            raise AgentCancelledException(f"Run {thread_id} cancelled by user")

    async def set_human_request(self, thread_id: str, request_data: HumanRequestData):
        """
        Store a structured Human Request (HITL).
        """
        request_dict = (
            request_data.model_dump()
            if isinstance(request_data, HumanRequestData)
            else request_data
        )

        # Validate request type against the known set.
        request_type = (
            request_dict.get("type") if isinstance(request_dict, dict) else None
        )
        valid_types = [t.value for t in HumanRequestType]
        if request_type not in valid_types:
            logger.warning(
                "[ActivityMonitor] Unknown request type: %s (expected one of %s)",
                request_type,
                valid_types,
            )

        success = await self._state_service.set_human_request(thread_id, request_dict)

        if success:
            # Publish HITL request + status change
            await system_bus.publish(
                HumanRequestEvent(
                    thread_id=thread_id,
                    action="create",
                    id=request_dict.get("id"),
                    prompt=request_dict.get("prompt"),
                    request_type=request_dict.get("type"),
                    options=request_dict.get("options"),
                    context=request_dict.get("context"),
                    default_value=request_dict.get("default_value"),
                    allow_cancel=request_dict.get("allow_cancel", True),
                    payload=request_dict.get("payload", {}),
                )
            )
            await system_bus.publish(
                SystemStatusEvent(thread_id=thread_id, status=ActivityStatus.INTERRUPTED)
            )

    async def clear_human_request(self, thread_id: str):
        """Clear human request upon resumption."""
        success = await self._state_service.clear_human_request(thread_id)

        if success:
            await system_bus.publish(
                HumanRequestEvent(thread_id=thread_id, action="clear")
            )
        await system_bus.publish(
            SystemStatusEvent(thread_id=thread_id, status=ActivityStatus.IDLE)
        )

    async def update_agent_state(
        self,
        thread_id: str,
        mode: str,
        task_name: str,
        task_status: str,
        details: dict[str, Any] | None = None,
        active_skills: list[dict] | None = None,
    ):
        """Update agent state and publish event."""
        state = AgentActivityState(
            mode=mode,
            task_name=task_name,
            task_status=task_status,
            details=details or {},
            active_skills=active_skills,
        )

        await self._state_service.update_agent_state(thread_id, state.model_dump())

        # Publish agent state event
        await system_bus.publish(
            AgentStateEvent(
                thread_id=thread_id,
                mode=mode,
                task_name=task_name,
                task_status=task_status,
                active_skills=active_skills,
            )
        )

    async def log_event(
        self, event_type: str, data: dict[str, Any], thread_id: str = "system"
    ):
        """Generic event logger for system and session events."""
        timestamp = time.time()
        payload = SystemLogPayload(type=event_type, data=data, timestamp=timestamp)

        # Log to a system list in cache for persistence
        # Use pipeline to make lpush+ltrim atomic
        pipe = cache.pipeline()
        pipe.lpush(f"system:logs:{event_type}", payload.model_dump_json())
        pipe.ltrim(f"system:logs:{event_type}", 0, 99)  # Keep last 100
        await pipe.execute()

        # Publish to the chat stream if it's a session event
        if thread_id != "system":
            await system_bus.publish(
                SystemLogEvent(thread_id=thread_id, log_type=event_type, log_data=data)
            )

    async def add_artifact(
        self,
        thread_id: str,
        name: str,
        artifact_type: str,
        status="created",
        path: str = None,
    ):
        """Add or update an artifact and publish event."""
        await self._state_service.add_artifact(
            thread_id, name, artifact_type, status, path
        )

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
                    path=target_art.get("path"),
                )
            )

    async def get_activity(self, thread_id: str):
        """Get full activity state for a thread."""
        return await self._state_service.get_state(thread_id)

    async def update_goal(self, thread_id: str, new_goal: str):
        """Update the main goal for a thread and publish the update to the UI."""
        if not thread_id:
            logger.warning(
                "[ActivityMonitor] update_goal called with empty/None thread_id — skipping."
            )
            return
        # 1. Update SQLite/database state
        await self._state_service.update_field(thread_id, "main_goal", new_goal)

        # 2. Publish the full activity state via the system event bus
        activity = await self.get_activity(thread_id)
        if activity:
            snapshot = (
                activity.model_dump() if hasattr(activity, "model_dump") else activity
            )
            from app.core.monitoring.event import ActivityStateRefreshedEvent

            event = ActivityStateRefreshedEvent(
                thread_id=thread_id, activity_state=snapshot
            )
            await system_bus.publish(event)
            logger.info(
                f"[ActivityMonitor] Session goal updated and state refreshed for thread {thread_id}: {new_goal}"
            )

    async def get_statuses(self, thread_ids: list[str]) -> dict[str, dict[str, str]]:
        """Batch fetch statuses and goals for multiple threads efficiently."""
        if not thread_ids:
            return {}

        async with session_scope() as session:
            stmt = select(
                AgentActivity.thread_id, AgentActivity.status, AgentActivity.main_goal
            ).where(AgentActivity.thread_id.in_(thread_ids))
            result = await session.execute(stmt)
            activity_map = {
                row[0]: {"status": row[1], "main_goal": row[2]} for row in result.all()
            }

        # Default missing threads to "idle" and empty goal
        for tid in thread_ids:
            if tid not in activity_map:
                activity_map[tid] = {"status": ActivityStatus.IDLE.value, "main_goal": ""}

        return activity_map

    async def record_task_update(self, task: "BackgroundTask"):
        """Record a background task update in the agent activity state.

        Maps background task lifecycle changes into the agent_state so the
        frontend activity indicator reflects ongoing background work (e.g.
        long-running shell commands, file operations).
        """
        from app.core.execution.terminal.background.schemas import TaskStatus

        thread_id = task.thread_id
        if not thread_id:
            return

        task_status = task.status
        if task_status is None:
            return

        title = task.title
        elapsed = task.elapsed_seconds

        if task_status == TaskStatus.PENDING:
            await self.update_agent_state(
                thread_id=thread_id,
                mode="Background Task",
                task_name=title,
                task_status="Pending...",
            )
        elif task_status == TaskStatus.RUNNING:
            await self.update_agent_state(
                thread_id=thread_id,
                mode="Background Task",
                task_name=title,
                task_status=f"Running... ({elapsed}s)",
            )
        elif task_status == TaskStatus.COMPLETED:
            await self.update_agent_state(
                thread_id=thread_id,
                mode="Background Task",
                task_name=title,
                task_status=f"Completed ({elapsed}s)",
            )
        elif task_status == TaskStatus.FAILED:
            await self.update_agent_state(
                thread_id=thread_id,
                mode="Background Task",
                task_name=title,
                task_status=f"Failed ({elapsed}s)",
                details={"error": task.error_message or ""},
            )
        elif task_status == TaskStatus.CANCELLED:
            await self.update_agent_state(
                thread_id=thread_id,
                mode="Background Task",
                task_name=title,
                task_status="Cancelled",
            )
        elif task_status == TaskStatus.TIMEOUT:
            await self.update_agent_state(
                thread_id=thread_id,
                mode="Background Task",
                task_name=title,
                task_status=f"Timed out after {elapsed}s",
            )


# Global Instance
activity_monitor = ActivityMonitor.get_instance()
