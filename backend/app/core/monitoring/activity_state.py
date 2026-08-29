"""Activity state service — manages agent activity state persistence."""

import json
import logging
import time
from datetime import timezone
from typing import Any

from pydantic import Field
from sqlalchemy import func, select

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models import AgentActivity, Message
from app.models.subagent import SubagentRun

logger = logging.getLogger(__name__)

_CANCELLATION_CACHE: dict[str, tuple[bool, float]] = {}
_CANCELLATION_CACHE_TTL_SECONDS = 0.5


class ActivityArtifact(DynamicBaseModel):
    """An artifact tracked during agent activity."""

    id: str
    name: str
    type: str
    status: str
    path: str | None = None
    icon: str = "FileCode"


class ActivityState(DynamicBaseModel):
    """Full activity state for an agent run."""

    status: str
    main_goal: str = ""
    updated_at: float = 0.0
    running_tools_count: int = 0
    artifacts: list[ActivityArtifact] = Field(default_factory=list)
    agent_state: dict = Field(default_factory=dict)
    verification: dict = Field(default_factory=dict)
    active_memories: list[dict] = Field(default_factory=list)
    human_request: dict | None = None
    final_outcome: str = ""
    subagents: list[dict] = Field(default_factory=list)


class ActivityStateService:
    """
    Service for managing agent activity state.

    Uses SQLite (AgentActivity table) for persistent storage.
    """

    def __init__(self, backend: Any | None = None):
        self._backend = backend

    @staticmethod
    def _get_session_scope():
        from app.infrastructure.database import session_scope

        return session_scope

    async def start_run(
        self,
        thread_id: str,
        main_goal: str = "",
        session=None,
        run_id: str | None = None,
    ) -> bool:
        """Initialize activity state for a new run."""
        if session is not None:
            return await self._start_run_with_session(
                thread_id, main_goal, session, run_id
            )

        async with self._get_session_scope()() as s:
            return await self._start_run_with_session(thread_id, main_goal, s, run_id)

    async def _start_run_with_session(
        self,
        thread_id: str,
        main_goal: str,
        session,
        run_id: str | None = None,
    ) -> bool:
        activity = await session.get(AgentActivity, thread_id)
        if activity is None:
            activity = AgentActivity(thread_id=thread_id)
            session.add(activity)

        activity.status = "running"
        # 记录当前 run，使 end_run 能校验 run_id 隔离，避免旧 run 的取消/结束
        # 覆盖新 run 的活动状态。
        activity.run_id = run_id
        activity.main_goal = main_goal
        activity.artifacts_json = json.dumps([])
        activity.agent_state_json = json.dumps({})
        activity.active_memories_json = json.dumps([])
        activity.human_request_json = None
        activity.final_outcome = ""
        # 新 run 开始时清空可能的旧取消缓存，避免下一轮 run_scope 读取到 stale 的
        # _CANCELLATION_CACHE（TTL 0.5s 内上一 run 的 check_cancellation 结果）。
        _CANCELLATION_CACHE.pop(thread_id, None)
        return True

    async def end_run(
        self,
        thread_id: str,
        status: str = "done",
        final_outcome: str | None = None,
        session=None,
        run_id: str | None = None,
    ) -> ActivityState:
        """Mark run as ended and return final state."""
        if session is not None:
            return await self._end_run_with_session(thread_id, status, final_outcome, session, run_id)

        async with self._get_session_scope()() as s:
            return await self._end_run_with_session(thread_id, status, final_outcome, s, run_id)

    async def _end_run_with_session(
        self,
        thread_id: str,
        status: str,
        final_outcome: str | None,
        session,
        run_id: str | None = None,
    ) -> ActivityState:
        activity = await session.get(AgentActivity, thread_id)
        if activity is None:
            return ActivityState(status=status)

        # run_id 隔离：带 run_id 的结束调用必须匹配当前 run。若传入的 run_id
        # 与表内（当前 run）不一致，说明是旧 run 的迟到取消/结束。DB 状态保持
        # 新 run 不变，但向调用方返回本次请求的真实终态（旧 run 的 run_end
        # 事件正确上报，而非当前新 run 的状态）。
        # 未传 run_id 的外部终结（如错误处理、A2A 回调）视为对当前 run 生效，放行。
        if (
            run_id is not None
            and activity.run_id is not None
            and activity.run_id != run_id
        ):
            logger.warning(
                "[activity] end_run(run_id=%s) mismatches current run_id=%s for thread %s; skipping state update",
                run_id,
                activity.run_id,
                thread_id,
            )
            return ActivityState(status=status)

        # Idempotent: skip if already in a terminal state
        if activity.status in ("done", "cancelled", "failed", "quota_exhausted"):
            return ActivityState(status=activity.status)

        if activity.status in ("quota_exhausted", "cancelled", "failed"):
            final_status = activity.status
        elif activity.status == "stopping":
            final_status = "cancelled"
        else:
            final_status = status
        activity.status = final_status
        if final_outcome:
            activity.final_outcome = final_outcome

        return ActivityState(status=final_status)

    async def get_state(self, thread_id: str) -> ActivityState:
        """Get lightweight activity state."""
        async with self._get_session_scope()() as session:
            activity = await session.get(AgentActivity, thread_id)
            if activity is None:
                return ActivityState(status="idle")

            try:
                running_count = await session.scalar(
                    select(func.count())
                    .select_from(Message)
                    .where(Message.thread_id == thread_id)
                    .where(Message.role == "tool")
                    .where(Message.status == "running")
                )

                artifacts_raw = json.loads(activity.artifacts_json or "[]")
                subagents = await self._load_subagents(session, thread_id)
                return ActivityState(
                    status=activity.status,
                    main_goal=activity.main_goal,
                    updated_at=activity.updated_at.replace(tzinfo=timezone.utc).timestamp() if activity.updated_at else 0.0,
                    running_tools_count=running_count or 0,
                    artifacts=[ActivityArtifact.model_validate(a) for a in artifacts_raw],
                    agent_state=json.loads(activity.agent_state_json or "{}"),
                    verification={},
                    active_memories=json.loads(activity.active_memories_json or "[]"),
                    human_request=json.loads(activity.human_request_json) if activity.human_request_json else None,
                    final_outcome=activity.final_outcome,
                    subagents=subagents,
                )
            except (json.JSONDecodeError, ValueError) as e:
                logger.exception(f"Failed to parse activity state for {thread_id}: {e}")
                return ActivityState(status="error")

    @staticmethod
    async def _load_subagents(session: Any, thread_id: str) -> list[dict]:
        """Recover subagent status from the SubagentRun table for the right panel.

        Frontend restores the live subagent panel from this on conversation load /
        reconnect (SSE lifecycle events only cover the current connection).
        """
        stmt = (
            select(SubagentRun)
            .where(SubagentRun.parent_thread_id == thread_id)
            .order_by(SubagentRun.started_at)
        )
        runs = (await session.execute(stmt)).scalars().all()
        subagents = []
        for r in runs:
            subagent_id = r.id.split("-sub-")[-1] if "-sub-" in r.id else r.id
            subagents.append(
                {
                    "subagent_id": subagent_id,
                    "subagent_thread_id": r.thread_id,
                    "instruction": r.instruction,
                    "status": r.status,
                    "result": r.result or "",
                    "error": r.error,
                }
            )
        return subagents

    async def update_field(self, thread_id: str, field: str, value: Any) -> bool:
        """Update a single field in the activity state."""
        if not isinstance(value, str):
            value = json.dumps(value) if isinstance(value, dict | list) else str(value)

        field_map = {
            "status": "status",
            "main_goal": "main_goal",
            "artifacts": "artifacts_json",
            "agent_state": "agent_state_json",
            "active_memories": "active_memories_json",
            "human_request": "human_request_json",
            "final_outcome": "final_outcome",
            "interrupt_reason": "human_request_json",
        }

        db_field = field_map.get(field)
        if db_field is None:
            logger.warning(f"Unknown activity field: {field}")
            return False

        async with self._get_session_scope()() as session:
            activity = await session.get(AgentActivity, thread_id)
            if activity is None:
                logger.warning(
                    f"[ActivityStateService] update_field('{field}') skipped: "
                    f"no AgentActivity record for thread_id='{thread_id}'. "
                    "Records must be created via start_run, not lazily on update."
                )
                return False
            setattr(activity, db_field, value)
        return True

    async def get_field(self, thread_id: str, field: str) -> Any | None:
        """Get a single field from activity state."""
        field_map = {
            "status": "status",
            "main_goal": "main_goal",
            "artifacts": "artifacts_json",
            "agent_state": "agent_state_json",
            "active_memories": "active_memories_json",
            "human_request": "human_request_json",
            "final_outcome": "final_outcome",
        }

        db_field = field_map.get(field)
        if db_field is None:
            return None

        async with self._get_session_scope()() as session:
            activity = await session.get(AgentActivity, thread_id)
            if activity is None:
                return None
            return getattr(activity, db_field)

    async def signal_stop(self, thread_id: str) -> bool:
        """Signal a run to stop."""
        async with self._get_session_scope()() as session:
            activity = await session.get(AgentActivity, thread_id)
            if activity is None:
                return False
            activity.status = "stopping"
        _CANCELLATION_CACHE.pop(thread_id, None)
        return True

    async def check_cancellation(self, thread_id: str, session=None) -> bool:
        """Check if run is marked for stopping."""
        now = time.time()
        cached = _CANCELLATION_CACHE.get(thread_id)
        if cached is not None:
            is_cancelled, expires_at = cached
            if now < expires_at:
                return is_cancelled

        if session:
            return await self._check_cancellation_with_session(thread_id, now, session)

        async with self._get_session_scope()() as s:
            return await self._check_cancellation_with_session(thread_id, now, s)

    async def _check_cancellation_with_session(self, thread_id: str, now: float, session) -> bool:
        result = await session.execute(
            select(AgentActivity.status).where(AgentActivity.thread_id == thread_id)
        )
        status = result.scalar_one_or_none()
        is_cancelled = status == "stopping"
        _CANCELLATION_CACHE[thread_id] = (
            is_cancelled,
            now + _CANCELLATION_CACHE_TTL_SECONDS,
        )
        return is_cancelled

    async def set_human_request(self, thread_id: str, request_data: dict) -> bool:
        """Store structured human request."""
        async with self._get_session_scope()() as session:
            activity = await session.get(AgentActivity, thread_id)
            if activity is None:
                return False
            activity.status = "interrupted"
            activity.human_request_json = json.dumps(request_data)
        return True

    async def clear_human_request(self, thread_id: str) -> bool:
        """Clear human request upon resumption."""
        async with self._get_session_scope()() as session:
            activity = await session.get(AgentActivity, thread_id)
            if activity is None:
                return False
            activity.status = "idle"
            activity.human_request_json = None
        return True

    async def update_agent_state(self, thread_id: str, state: dict) -> bool:
        """Update agent state."""
        async with self._get_session_scope()() as session:
            activity = await session.get(AgentActivity, thread_id)
            if activity is None:
                activity = AgentActivity(thread_id=thread_id)
                session.add(activity)

            if activity.agent_state_json:
                try:
                    prev_state = json.loads(activity.agent_state_json)
                    if state.get("active_skills") is None and prev_state.get("active_skills") is not None:
                        state["active_skills"] = prev_state["active_skills"]
                except Exception as e:
                    logger.debug("Suppressed error: %s", e, exc_info=True)

            activity.agent_state_json = json.dumps(state)
        return True

    async def add_artifact(
        self,
        thread_id: str,
        name: str,
        artifact_type: str,
        status: str = "created",
        path: str = None,
    ) -> bool:
        """Add or update an artifact."""
        async with self._get_session_scope()() as session:
            activity = await session.get(AgentActivity, thread_id)
            if activity is None:
                activity = AgentActivity(thread_id=thread_id)
                session.add(activity)

            try:
                artifacts = json.loads(activity.artifacts_json or "[]")
            except (json.JSONDecodeError, TypeError):
                artifacts = []

            for art in artifacts:
                if art.get("name") == name:
                    art["status"] = "modified"
                    activity.artifacts_json = json.dumps(artifacts)
                    return True

            new_artifact = ActivityArtifact(
                id=str(len(artifacts) + 1),
                name=name,
                type=artifact_type,
                status=status,
                path=path,
                icon="FileCode",
            )
            artifacts.append(new_artifact.model_dump())
            activity.artifacts_json = json.dumps(artifacts)
        return True
