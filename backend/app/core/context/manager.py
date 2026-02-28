import contextvars
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.infrastructure.database.redis import redis_client


# ==========================================
# Core Context Definition
# ==========================================


@dataclass
class EvoContext:
    """
    Unified Execution Context for EvoLoop.
    Holds request-scoped or task-scoped information.
    """
    request_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: float = field(default_factory=lambda: __import__("time").time())

    # Identity
    user_id: str | None = None
    project_id: int | None = None
    thread_id: str | None = None

    # Execution Environment
    working_directory: str | None = None
    command_id: int | None = None   # For EvoCloud command tracing
    trace_id: str | None = None     # Distributed trace ID

    # Feature Flags / Runtime Config
    is_dry_run: bool = False
    language: str = "en"

    # [Phase 1: Subconscious Pool]
    # Dynamically injected context from Environment/Learning plugins via EventBus
    short_term_memory: list[str] = field(default_factory=list)
    active_boundaries: list[str] = field(default_factory=list)
    spatial_awareness: list[str] | dict[str, Any] = field(default_factory=list)
    environment_summaries: list[str] | dict[str, Any] = field(default_factory=list)
    memory_replay: list[str] | dict[str, Any] = field(default_factory=list)
    identity_rules: list[str] = field(default_factory=list)
    environment_block: str | None = None
    
    # [Phase 4: Intent-Aware Context]
    # Tracks the "active" application, entities, or elements mentioned in recent dialogue
    entity_focus: list[str] = field(default_factory=list)

    # Extra Metadata (Plugins, etc.)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert the context to a serializable dictionary."""
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "thread_id": self.thread_id,
            "working_directory": self.working_directory,
            "command_id": self.command_id,
            "trace_id": self.trace_id,
            "is_dry_run": self.is_dry_run,
            "language": self.language,
            "short_term_memory": self.short_term_memory,
            "active_boundaries": self.active_boundaries,
            "spatial_awareness": self.spatial_awareness,
            "environment_summaries": self.environment_summaries,
            "memory_replay": self.memory_replay,
            "identity_rules": self.identity_rules,
            "environment_block": self.environment_block,
            "entity_focus": self.entity_focus,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvoContext":
        """Reconstruct a context from a dictionary."""
        ctx = cls()
        for key, value in data.items():
            if hasattr(ctx, key):
                setattr(ctx, key, value)
        return ctx


# ==========================================
# ContextVars Storage
# ==========================================

_context_var = contextvars.ContextVar("evo_context", default=None)


class ContextManager:
    """
    Static manager for access to the current EvoContext.
    """

    @staticmethod
    def current() -> EvoContext:
        """
        Get the current context. If none exists, returns a default empty context.
        """
        ctx = _context_var.get()
        if ctx is None:
            # Return a default context to avoid crashes, but warn if strict mode?
            # For now, safe default.
            return EvoContext(request_id="global-fallback")
        return ctx

    @staticmethod
    def set(ctx: EvoContext) -> contextvars.Token:
        """
        Set the current context. Returns a token to reset it later.
        """
        return _context_var.set(ctx)

    @staticmethod
    def reset(token: contextvars.Token):
        """
        Reset the context using a token.
        """
        _context_var.reset(token)

    @staticmethod
    def get_var(key: str, default: Any = None) -> Any:
        """
        Helper to get a attribute from current context dynamically.
        Compatibility helper for old code using dict-like access.
        """
        ctx = ContextManager.current()
        if hasattr(ctx, key):
            return getattr(ctx, key) or default
        return ctx.metadata.get(key, default)

    @staticmethod
    async def save_to_redis(thread_id: str) -> None:
        """
        Phase 4 Autonomy: Persist the current context to Redis using the thread_id.
        Uses HSET for individual fields to allow for partial updates and prevent 
        serialization bottlenecks.
        """
        ctx = ContextManager.current()
        if ctx.request_id == "global-fallback":
            return

        ctx.thread_id = thread_id
        key = f"evo:context:{thread_id}"

        try:
            # Map context to flat dictionary for HSET
            # Convert lists/dicts to JSON strings within fields
            data = ctx.to_dict()
            hset_data = {}
            for k, v in data.items():
                if isinstance(v, (list, dict)):
                    hset_data[k] = json.dumps(v)
                elif v is None:
                    hset_data[k] = ""
                else:
                    hset_data[k] = str(v)

            if hset_data:
                await redis_client.hset(key, mapping=hset_data)
                # Set expiration on the hash key (7 days)
                await redis_client.expire(key, 604800)

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to save context to Redis (HSET): {e}")

    @staticmethod
    async def load_from_redis(thread_id: str) -> EvoContext | None:
        """
        Phase 4 Autonomy: Load context from Redis using the thread_id and set it as current.
        Supports Hash mapping (HGETALL).
        """
        key = f"evo:context:{thread_id}"
        try:
            data = await redis_client.hgetall(key)
            if data:
                # Convert potential bytes to strings and parse JSON for collections
                reconstructed = {}
                # Field types expected by from_dict/dataclass
                list_fields = {
                    "short_term_memory", "active_boundaries", "identity_rules", "entity_focus"
                }
                # Support both dict and list for flexible context fields
                flexible_fields = {"spatial_awareness", "environment_summaries", "memory_replay"}
                dict_fields = {"metadata"}
                
                for k, v in data.items():
                    if isinstance(v, bytes):
                        v = v.decode("utf-8")
                    
                    if k in list_fields or k in flexible_fields or k in dict_fields:
                        try:
                            reconstructed[k] = json.loads(v) if v else (
                                [] if k in list_fields else ({} if k in dict_fields or k in flexible_fields else [])
                            )
                        except Exception:
                            reconstructed[k] = [] if k in list_fields else {}
                    elif k == "timestamp":
                        reconstructed[k] = float(v) if v else 0.0
                    elif k == "is_dry_run":
                        reconstructed[k] = v.lower() == "true"
                    elif k == "project_id" or k == "command_id":
                        reconstructed[k] = int(v) if v and v.isdigit() else None
                    else:
                        reconstructed[k] = v if v != "" else None

                ctx = EvoContext.from_dict(reconstructed)
                ContextManager.set(ctx)
                return ctx
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load context from Redis (HGETALL): {e}")

        return None


# Global Accessor Alias
get_context = ContextManager.current
