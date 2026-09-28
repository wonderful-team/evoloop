"""
EvoLoop Hooks - Lifecycle event management inspired by Claude Code.

This module provides a hook system for capturing lifecycle events.
"""

# Import side-effect hook modules (auto-register on import)
from app.core.engine.hooks import authorization, security  # noqa: F401

# Import core classes from the core module
from app.core.engine.hooks.core import (
    HookEvent,
    HookSystem,
    hook_system,
    setup_default_hooks,
)
from app.core.engine.hooks.schemas import HookContext, HookResult, ToolInput, ToolResult

__all__ = [
    "HookEvent",
    "HookContext",
    "HookResult",
    "HookSystem",
    "ToolInput",
    "ToolResult",
    "hook_system",
    "setup_default_hooks",
]
