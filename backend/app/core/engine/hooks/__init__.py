"""
EvoLoop Hooks - Lifecycle event management inspired by Claude Code.

This module provides a hook system for capturing lifecycle events.
"""

# Import core classes from the core module
from app.core.engine.hooks.core import (
    HookEvent,
    HookContext,
    HookResult,
    HookSystem,
    hook_system,
    setup_default_hooks,
)

# Import security hooks (auto-register on import)
from app.core.engine.hooks import security

__all__ = [
    "HookEvent",
    "HookContext",
    "HookResult",
    "HookSystem",
    "hook_system",
    "setup_default_hooks",
]
