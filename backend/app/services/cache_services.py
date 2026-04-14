"""
High-level cache services for business logic.

These services provide domain-specific caching operations without
exposing the underlying cache implementation details.
"""

import json
import logging
from typing import Any

from pydantic import Field

from app.infrastructure.cache import get_cache
from app.infrastructure.cache.abstract import Cache
from app.infrastructure.pydantic_base import DynamicBaseModel

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


class ActivityStep(DynamicBaseModel):
    """A single step in the agent activity."""
    id: int
    name: str
    status: str
    type: str = "node"
    parent_id: int | None = None
    start_time: float
    end_time: float | None = None
    time: str = "0s"
    input: dict | None = None
    details: str | None = None


class ActivityArtifact(DynamicBaseModel):
    """An artifact tracked during agent activity."""
    id: int
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
    steps: list[ActivityStep] = Field(default_factory=list)
    artifacts: list[ActivityArtifact] = Field(default_factory=list)
    agent_state: dict = Field(default_factory=dict)
    verification: dict = Field(default_factory=dict)
    active_memories: list[dict] = Field(default_factory=list)
    human_request: dict | None = None
    final_outcome: str = ""


class ActivityStateService:
    """
    Service for managing agent activity state.
    
    Replaces direct cache usage in ActivityMonitor.
    
    Keys:
        activity:{thread_id} -> Hash with state fields
    """

    KEY_PREFIX = "activity"
    DEFAULT_TTL = 86400  # 24 hours

    def __init__(self, backend: Cache | None = None):
        self._cache = backend or get_cache()

    def _key(self, thread_id: str) -> str:
        return f"{self.KEY_PREFIX}:{thread_id}"

    async def start_run(self, thread_id: str, main_goal: str = "处理用户请求") -> bool:
        """Initialize activity state for a new run."""
        import time
        data = {
            "status": "running",
            "main_goal": main_goal,
            "agent_state": json.dumps({}),
            "verification": json.dumps({}),
            "steps": json.dumps([]),
            "artifacts": json.dumps([]),
            "active_memories": json.dumps([]),
            "final_outcome": "",
            "updated_at": str(time.time()),
        }
        await self._cache.hset(self._key(thread_id), mapping=data)
        await self._cache.expire(self._key(thread_id), self.DEFAULT_TTL)
        return True

    async def end_run(self, thread_id: str, status: str = "done", final_outcome: str | None = None) -> ActivityState:
        """Mark run as ended and return final state."""
        import time
        key = self._key(thread_id)
        
        # Get current status to handle stopping->cancelled
        current = await self._cache.hget(key, "status")
        final_status = "cancelled" if current == "stopping" else status
        
        mapping = {
            "status": final_status,
            "updated_at": str(time.time())
        }
        if final_outcome:
            mapping["final_outcome"] = final_outcome
        
        await self._cache.hset(key, mapping=mapping)
        
        # Mark running steps as done/cancelled
        steps_json = await self._cache.hget(key, "steps")
        if steps_json:
            steps = json.loads(steps_json) if isinstance(steps_json, str) else steps_json
            modified = False
            for step in steps:
                if step.get("status") == "running":
                    step["status"] = "cancelled" if final_status == "cancelled" else "done"
                    modified = True
            if modified:
                await self._cache.hset(key, "steps", json.dumps(steps))

        return await self.get_state(thread_id)

    async def get_state(self, thread_id: str) -> ActivityState:
        """Get full activity state."""
        key = self._key(thread_id)
        data = await self._cache.hgetall(key)

        if not data:
            return ActivityState(status="idle")

        # Parse JSON fields
        try:
            steps_raw = json.loads(data.get("steps", "[]"))
            artifacts_raw = json.loads(data.get("artifacts", "[]"))
            return ActivityState(
                status=data.get("status", "unknown"),
                main_goal=data.get("main_goal", ""),
                updated_at=float(data.get("updated_at", 0)),
                steps=[ActivityStep.model_validate(s) for s in steps_raw],
                artifacts=[ActivityArtifact.model_validate(a) for a in artifacts_raw],
                agent_state=json.loads(data.get("agent_state", "{}")),
                verification=json.loads(data.get("verification", "{}")),
                active_memories=json.loads(data.get("active_memories", "[]")),
                human_request=json.loads(data.get("human_request")) if data.get("human_request") else None,
                final_outcome=data.get("final_outcome", ""),
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse activity state for {thread_id}: {e}")
            return ActivityState(status="error")

    async def update_field(self, thread_id: str, field: str, value: Any) -> bool:
        """Update a single field in the activity state."""
        if not isinstance(value, str):
            value = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        return await self._cache.hset(self._key(thread_id), field, value) > 0

    async def get_field(self, thread_id: str, field: str) -> Any | None:
        """Get a single field from activity state."""
        return await self._cache.hget(self._key(thread_id), field)

    async def signal_stop(self, thread_id: str) -> bool:
        """Signal a run to stop."""
        if await self._cache.exists(self._key(thread_id)):
            await self._cache.hset(
                self._key(thread_id),
                mapping={
                    "status": "stopping",
                    "updated_at": str(__import__('time').time())
                }
            )
            return True
        return False

    async def check_cancellation(self, thread_id: str) -> bool:
        """Check if run is marked for stopping."""
        status = await self._cache.hget(self._key(thread_id), "status")
        return status == "stopping"

    async def set_interrupted(self, thread_id: str, reason: str = "awaiting_human_input") -> bool:
        """Mark run as interrupted."""
        key = self._key(thread_id)
        if await self._cache.exists(key):
            await self._cache.hset(
                key,
                mapping={
                    "status": "interrupted",
                    "interrupt_reason": reason,
                    "updated_at": str(__import__('time').time())
                }
            )
            return True
        return False

    async def set_human_request(self, thread_id: str, request_data: dict) -> bool:
        """Store structured human request."""
        key = self._key(thread_id)
        if not await self._cache.exists(key):
            return False
        
        await self._cache.hset(
            key,
            mapping={
                "status": "interrupted",
                "human_request": json.dumps(request_data),
                "interrupt_reason": request_data.get("prompt", "Human Input Required"),
                "updated_at": str(__import__('time').time())
            }
        )
        return True

    async def clear_human_request(self, thread_id: str) -> bool:
        """Clear human request upon resumption."""
        key = self._key(thread_id)
        if await self._cache.exists(key):
            await self._cache.hset(
                key,
                mapping={
                    "status": "idle",  # HITL cleared, agent not yet resumed
                    "human_request": "",
                    "interrupt_reason": "",
                    "updated_at": str(__import__('time').time())
                }
            )
            return True
        return False

    async def add_step(self, thread_id: str, name: str, step_type: str = "node", parent_id: int = None, input_data: dict = None) -> int | None:
        """Add a new step to the activity."""
        import time
        key = self._key(thread_id)
        lock_key = f"lock:{key}"

        async with self._cache.lock(lock_key, timeout=2.0, blocking_timeout=1.0):
            if not await self._cache.exists(key):
                return None

            steps_json = await self._cache.hget(key, "steps")
            steps = json.loads(steps_json) if steps_json else []

            if not name:
                return None

            step_id = len(steps) + 1
            new_step = ActivityStep(
                id=step_id,
                name=name,
                status="running",
                type=step_type,
                parent_id=parent_id,
                start_time=time.time(),
                time="0s",
                input=input_data,
            )
            steps.append(new_step.model_dump())

            await self._cache.hset(
                key,
                mapping={
                    "steps": json.dumps(steps),
                    "updated_at": str(time.time())
                }
            )
            return step_id

    async def complete_step(self, thread_id: str, step_id: int) -> bool:
        """Mark a step as completed."""
        import time
        key = self._key(thread_id)
        lock_key = f"lock:{key}"
        
        async with self._cache.lock(lock_key, timeout=2.0, blocking_timeout=1.0):
            steps_json = await self._cache.hget(key, "steps")
            if not steps_json:
                return False
            
            steps = json.loads(steps_json) if isinstance(steps_json, str) else steps_json
            for step in steps:
                if step.get("id") == step_id:
                    step["status"] = "done"
                    step["end_time"] = time.time()
                    await self._cache.hset(
                        key,
                        mapping={
                            "steps": json.dumps(steps),
                            "updated_at": str(time.time())
                        }
                    )
                    return True
            return False

    async def update_agent_state(self, thread_id: str, state: dict) -> bool:
        """Update agent state."""
        key = self._key(thread_id)
        await self._cache.hset(key, "agent_state", json.dumps(state))
        return True

    async def add_artifact(self, thread_id: str, name: str, artifact_type: str, status: str = "created", path: str = None) -> bool:
        """Add or update an artifact."""
        import time
        key = self._key(thread_id)

        arts_json = await self._cache.hget(key, "artifacts")
        artifacts = json.loads(arts_json) if arts_json else []

        # Check if exists
        for art in artifacts:
            if art["name"] == name:
                art["status"] = "modified"
                await self._cache.hset(
                    key,
                    mapping={
                        "artifacts": json.dumps(artifacts),
                        "updated_at": str(time.time())
                    }
                )
                return True

        # Add new
        new_artifact = ActivityArtifact(
            id=len(artifacts) + 1,
            name=name,
            type=artifact_type,
            status=status,
            path=path,
            icon="FileCode",
        )
        artifacts.append(new_artifact.model_dump())

        await self._cache.hset(
            key,
            mapping={
                "artifacts": json.dumps(artifacts),
                "updated_at": str(time.time())
            }
        )
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
