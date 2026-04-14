import contextvars
import json
import time
from typing import Any, Dict, List, Optional, Union

from pydantic import Field

from app.core.exceptions import GlobalModeError
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.services.cache_services import ContextCacheService
from app.utils.id import gen_uuid


class ContextMetadata(DynamicBaseModel):
    """Dynamic metadata attached to an EvoContext."""


# ==========================================
# Core Context Definition
# ==========================================


class EvoContext(DynamicBaseModel):
    """
    Unified Execution Context for EvoLoop.
    Holds request-scoped or task-scoped information.
    """
    request_id: str = Field(default_factory=gen_uuid)
    timestamp: float = Field(default_factory=time.time)

    # Identity
    user_id: Optional[str] = None
    project_id: Optional[int] = None
    thread_id: Optional[str] = None

    # Execution Environment
    working_directory: Optional[str] = None
    command_id: Optional[int] = None   # For EvoCloud command tracing
    trace_id: Optional[str] = None     # Distributed trace ID

    # Feature Flags / Runtime Config
    is_dry_run: bool = False
    language: str = "en"

    # [Subconscious Pool]
    # Dynamically injected context from Environment/Learning plugins via EventBus
    short_term_memory: List[str] = Field(default_factory=list)
    active_boundaries: List[str] = Field(default_factory=list)
    spatial_awareness: Union[List[str], Dict[str, Any]] = Field(default_factory=list)
    environment_summaries: Union[List[str], Dict[str, Any]] = Field(default_factory=list)
    memory_replay: Union[List[str], Dict[str, Any]] = Field(default_factory=list)
    identity_rules: List[str] = Field(default_factory=list)
    environment_block: Optional[str] = None
    
    # Extra Metadata (Plugins, etc.)
    metadata: ContextMetadata = Field(default_factory=ContextMetadata)

    def to_dict(self) -> Dict[str, Any]:
        """Legacy compatibility method."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvoContext":
        """Legacy compatibility method."""
        return cls.model_validate(data)


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
    def resolve_project_id(explicit_id: int | None = None, allow_global: bool = False, request_temp: bool = False) -> int:
        """
        Resolve project ID from explicit parameter or current context.

        This method handles the logic of determining which project ID to use,
        with proper handling of global mode (project_id=0).

        Args:
            explicit_id: Explicitly provided project_id from tool arguments
            allow_global: If False (default), raises GlobalModeError when in global mode
                         If True, allows returning 0 for global mode operations
            request_temp: If True and in global mode, allows returning 0 as a signal
                         to request a temporary project from user (for this call only)

        Returns:
            int: The resolved project ID to use (0 means global mode or temp project needed)

        Raises:
            GlobalModeError: If the resolved project_id is 0 or None and allow_global is False
                              and request_temp is False

        Resolution order:
        1. explicit_id if provided and not 0
        2. context.project_id if set and not 0
        3. If allow_global=True and any above is 0, return 0
        4. If request_temp=True and in global mode, return 0 (caller should handle temp project)
        5. If allow_global=False and any above is 0/None, raise GlobalModeError
        """
        # Priority 1: Use explicit ID if provided (including 0 for global mode override)
        if explicit_id is not None:
            if explicit_id == 0:
                if allow_global:
                    return 0
                raise GlobalModeError(
                    "Explicit project_id=0 (global mode) provided, but this operation requires a specific project."
                )
            return explicit_id

        # Priority 2: Check context
        ctx = ContextManager.current()
        ctx_pid = ctx.project_id

        if ctx_pid is not None:
            if ctx_pid == 0:
                if allow_global:
                    return 0
                raise GlobalModeError(
                    "Currently in global mode. Please switch to a specific project to use this feature."
                )
            return ctx_pid

        # Priority 3: No project ID found
        if allow_global:
            return 0

        # Priority 4: Allow returning 0 to signal temp project request
        if request_temp:
            return 0

        raise GlobalModeError(
            "No project context available. Please specify a project_id or switch to a project."
        )

    @staticmethod
    async def save_to_redis(thread_id: str) -> None:
        """
        Persist the current context to cache using the thread_id.
        Uses HSET for individual fields to allow for partial updates and prevent 
        serialization bottlenecks.
        """
        ctx = ContextManager.current()
        if ctx.request_id == "global-fallback":
            return

        # Use existing thread_id (e.g. from state) if available, 
        # otherwise use the provided one (e.g. from config)
        thread_id = ctx.thread_id or thread_id
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
                cache_service = ContextCacheService()
                await cache_service.save_context(thread_id, hset_data)

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to save context to cache (HSET): {e}")

    @staticmethod
    async def load_from_redis(thread_id: str) -> EvoContext | None:
        """
        Load context from cache using the thread_id and set it as current.
        Supports Hash mapping (HGETALL).
        """
        try:
            cache_service = ContextCacheService()
            data = await cache_service.load_context(thread_id)
            if data:
                # Convert potential bytes to strings and parse JSON for collections
                reconstructed = {}
                # Field types expected by from_dict/dataclass
                list_fields = {
                    "short_term_memory", "active_boundaries", "identity_rules"
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
                        reconstructed[k] = str(v).lower() == "true"
                    elif k == "project_id" or k == "command_id":
                        reconstructed[k] = int(v) if v and str(v).isdigit() else None
                    else:
                        reconstructed[k] = v if v != "" else None

                ctx = EvoContext.from_dict(reconstructed)
                ContextManager.set(ctx)
                return ctx
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load context from cache (HGETALL): {e}")

        return None


# Global Accessor Alias
get_context = ContextManager.current
