import contextvars
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.core.exceptions import GlobalModeError


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


# Global Accessor Alias
get_context = ContextManager.current
