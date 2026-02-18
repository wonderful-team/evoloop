import contextvars
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from uuid import uuid4

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
    
    # Extra Metadata (Plugins, etc.)
    metadata: Dict[str, Any] = field(default_factory=dict)


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


# Global Accessor Alias
get_context = ContextManager.current
