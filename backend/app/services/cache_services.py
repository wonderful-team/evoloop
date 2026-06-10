"""
High-level cache services for business logic.

These services provide domain-specific caching operations without
exposing the underlying cache implementation details.
"""

import json
import logging
import time
from typing import Any

from pydantic import Field
from sqlalchemy import select, func

from app.infrastructure.cache import get_cache
from app.infrastructure.cache.abstract import Cache
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models import AgentActivity, Message

logger = logging.getLogger(__name__)


class UserCacheService:
    """
    Service for caching user data.

    Keys:
        evoloop:user:{member_id} -> User data dict
    """

    KEY_PREFIX = "evoloop:user"
    DEFAULT_TTL = 86400  # 24 hours

    def __init__(self, backend: Cache | None = None):
        self._cache = backend or get_cache()

    def _key(self, member_id: str | int) -> str:
        return f"{self.KEY_PREFIX}:{member_id}"

    async def get_user(self, member_id: str | int) -> dict | None:
        """Get cached user data by member ID."""
        data = await self._cache.get(self._key(member_id))
        if data is None:
            return None
        # Handle both JSON string and dict
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid user cache data for {member_id}")
                return None
        return data if isinstance(data, dict) else None

    async def set_user(self, member_id: str | int, user_data: dict, ttl: int | None = None) -> bool:
        """Cache user data."""
        return await self._cache.set(
            self._key(member_id),
            user_data,
            ex=ttl or self.DEFAULT_TTL
        )

    async def delete_user(self, member_id: str | int) -> bool:
        """Delete cached user data."""
        return await self._cache.delete(self._key(member_id)) > 0


class RateLimitService:
    """
    Service for rate limiting.

    Keys:
        ratelimit:{endpoint}:{identifier} -> Request count
    """

    KEY_PREFIX = "ratelimit"
    DEFAULT_WINDOW = 86400  # 24 hours

    def __init__(self, backend: Cache | None = None):
        self._cache = backend or get_cache()

    def _key(self, endpoint: str, identifier: str) -> str:
        return f"{self.KEY_PREFIX}:{endpoint}:{identifier}"

    async def increment(self, endpoint: str, identifier: str, window: int | None = None) -> int:
        """Increment request count and return new value."""
        key = self._key(endpoint, identifier)
        count = await self._cache.incr(key)
        if count == 1:
            # First request, set expiration
            await self._cache.expire(key, window or self.DEFAULT_WINDOW)
        return count

    async def get_count(self, endpoint: str, identifier: str) -> int:
        """Get current request count."""
        count = await self._cache.get(self._key(endpoint, identifier))
        return int(count) if count else 0

    async def reset(self, endpoint: str, identifier: str) -> bool:
        """Reset rate limit for identifier."""
        return await self._cache.delete(self._key(endpoint, identifier)) > 0


class LinkTokenService:
    """
    Service for temporary link tokens.

    Keys:
        evoloop:link:token -> Token data
    """

    KEY_PREFIX = "evoloop:link"

    def __init__(self, backend: Cache | None = None):
        self._cache = backend or get_cache()

    async def store_token(self, token_name: str, token_data: str, ttl: int = 3600) -> bool:
        """Store a link token."""
        return await self._cache.set(
            f"{self.KEY_PREFIX}:{token_name}",
            token_data,
            ex=ttl
        )

    async def get_token(self, token_name: str) -> str | None:
        """Get a link token."""
        data = await self._cache.get(f"{self.KEY_PREFIX}:{token_name}")
        return data if isinstance(data, str) else None


class ActivityArtifact(DynamicBaseModel):
    """An artifact tracked during agent activity."""
    id: str
    name: str
    type: str
    status: str
    path: str | None = None
    icon: str = "FileCode"


class ActivityState(DynamicBaseModel):
    """Full activity state for an agent run.

    Phase 3 redesign: steps are no longer returned here.
    Tool messages are sent as flat role="tool" messages via SSE.
    This model only returns lightweight run metadata.
    """
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


# ---------------------------------------------------------------------------
# In-process cancellation check cache
# ---------------------------------------------------------------------------
# Stores {thread_id: (is_stopping: bool, monotonic_ts: float)}
# TTL is intentionally short (2 s) so users see Stop take effect quickly.
_cancel_cache: dict[str, tuple[bool, float]] = {}
_CANCEL_CACHE_TTL: float = 2.0  # seconds


class ActivityStateService:
    """
    Service for managing agent activity state.

    Uses SQLite (AgentActivity table) for persistent storage.
    Replaces the previous FileCache-based implementation for better
    performance and reliability in embedded mode.
    """

    def __init__(self, backend: Cache | None = None):
        # backend is kept for API compatibility but no longer used
        self._backend = backend

    @staticmethod
    def _get_session_scope():
        from app.infrastructure.database.sql.database import session_scope
        return session_scope

    async def start_run(self, thread_id: str, main_goal: str = "") -> bool:
        """Initialize activity state for a new run."""
        async with self._get_session_scope()() as session:
            activity = await session.get(AgentActivity, thread_id)
            if activity is None:
                activity = AgentActivity(thread_id=thread_id)
                session.add(activity)
            
            # Reset status to 'running' for the new lifecycle.
            # This ensures that a 'Stop' signal from a previous run does not 
            # prematurely cancel the new run (e.g. during a Retry).
            activity.status = "running"
            
            activity.main_goal = main_goal
            activity.artifacts_json = json.dumps([])
            activity.agent_state_json = json.dumps({})
            activity.active_memories_json = json.dumps([])
            activity.human_request_json = None
            activity.final_outcome = ""
        return True

    async def end_run(self, thread_id: str, status: str = "done", final_outcome: str | None = None) -> ActivityState:
        """Mark run as ended and return final state."""

        async with self._get_session_scope()() as session:
            activity = await session.get(AgentActivity, thread_id)
            if activity is None:
                return ActivityState(status=status)

            if activity.status in ("quota_exhausted", "cancelled", "failed"):
                final_status = activity.status
            elif activity.status == "stopping":
                final_status = "cancelled"
            else:
                final_status = status
            activity.status = final_status
            if final_outcome:
                activity.final_outcome = final_outcome

        return await self.get_state(thread_id)

    async def get_state(self, thread_id: str) -> ActivityState:
        """Get lightweight activity state.

        Phase 3 redesign: steps are no longer returned here.
        Steps are now part of the Message model and travel via SSE
        message events. Callers that need step details should fetch
        the conversation messages instead.
        """
        async with self._get_session_scope()() as session:
            activity = await session.get(AgentActivity, thread_id)
            if activity is None:
                return ActivityState(status="idle")

            try:
                # Only count running tools (lightweight — no step reconstruction)
                running_count = await session.scalar(
                    select(func.count())
                    .select_from(Message)
                    .where(Message.thread_id == thread_id)
                    .where(Message.role == "tool")
                    .where(Message.status == "running")
                )

                artifacts_raw = json.loads(activity.artifacts_json or "[]")
                return ActivityState(
                    status=activity.status,
                    main_goal=activity.main_goal,
                    updated_at=activity.updated_at.timestamp() if activity.updated_at else 0,
                    running_tools_count=running_count or 0,
                    artifacts=[ActivityArtifact.model_validate(a) for a in artifacts_raw],
                    agent_state=json.loads(activity.agent_state_json or "{}"),
                    verification={},
                    active_memories=json.loads(activity.active_memories_json or "[]"),
                    human_request=json.loads(activity.human_request_json) if activity.human_request_json else None,
                    final_outcome=activity.final_outcome,
                )
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse activity state for {thread_id}: {e}")
                return ActivityState(status="error")

    async def update_field(self, thread_id: str, field: str, value: Any) -> bool:
        """Update a single field in the activity state."""
        if not isinstance(value, str):
            value = json.dumps(value) if isinstance(value, (dict, list)) else str(value)

        field_map = {
            "status": "status",
            "main_goal": "main_goal",
            "artifacts": "artifacts_json",
            "agent_state": "agent_state_json",
            "active_memories": "active_memories_json",
            "human_request": "human_request_json",
            "final_outcome": "final_outcome",
            "interrupt_reason": "human_request_json",  # stored inside human_request or ignored
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
        # Eagerly update the in-process cache so check_cancellation returns
        # True immediately on the same process without waiting for the TTL.
        _cancel_cache[thread_id] = (True, time.monotonic())
        return True

    async def check_cancellation(self, thread_id: str) -> bool:
        """Check if run is marked for stopping.

        Uses a short in-process TTL cache to avoid a DB round-trip on every
        ReAct step. The cache is invalidated eagerly by signal_stop().
        """
        now = time.monotonic()
        cached = _cancel_cache.get(thread_id)
        if cached is not None:
            is_stopping, ts = cached
            if now - ts < _CANCEL_CACHE_TTL:
                return is_stopping

        # Cache miss or expired — query the DB
        async with self._get_session_scope()() as session:
            activity = await session.get(AgentActivity, thread_id)
            if activity is None:
                return False
            is_stopping = activity.status == "stopping"

        _cancel_cache[thread_id] = (is_stopping, now)
        return is_stopping

    async def set_interrupted(self, thread_id: str, reason: str = "awaiting_human_input") -> bool:
        """Mark run as interrupted."""
        async with self._get_session_scope()() as session:
            activity = await session.get(AgentActivity, thread_id)
            if activity is None:
                return False
            activity.status = "interrupted"
            # Store reason in human_request_json as a fallback
            existing_hr = activity.human_request_json
            if existing_hr:
                try:
                    hr = json.loads(existing_hr)
                    hr["interrupt_reason"] = reason
                    activity.human_request_json = json.dumps(hr)
                except (json.JSONDecodeError, TypeError):
                    pass
        return True

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
            
            # Preserve active_skills if the incoming state omits it (e.g. Supervisor status updates)
            if activity.agent_state_json:
                try:
                    prev_state = json.loads(activity.agent_state_json)
                    if state.get("active_skills") is None and prev_state.get("active_skills") is not None:
                        state["active_skills"] = prev_state["active_skills"]
                except Exception:
                    pass

            activity.agent_state_json = json.dumps(state)
        return True

    async def add_artifact(self, thread_id: str, name: str, artifact_type: str, status: str = "created", path: str = None) -> bool:
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

            # Check if exists
            for art in artifacts:
                if art.get("name") == name:
                    art["status"] = "modified"
                    activity.artifacts_json = json.dumps(artifacts)
                    return True

            # Add new
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


class ContextCacheService:
    """
    Service for caching EvoContext between agent runs.

    Keys:
        evoloop:context:{thread_id} -> Context data
    """

    KEY_PREFIX = "evoloop:context"
    DEFAULT_TTL = 604800  # 7 days

    def __init__(self, backend: Cache | None = None):
        self._cache = backend or get_cache()

    def _key(self, thread_id: str) -> str:
        return f"{self.KEY_PREFIX}:{thread_id}"

    async def save_context(self, thread_id: str, context_data: dict) -> bool:
        """Save context data."""
        return await self._cache.hset(
            self._key(thread_id),
            mapping=context_data
        ) > 0

    async def load_context(self, thread_id: str) -> dict | None:
        """Load context data."""
        return await self._cache.hgetall(self._key(thread_id))

    async def delete_context(self, thread_id: str) -> bool:
        """Delete cached context."""
        return await self._cache.delete(self._key(thread_id)) > 0
