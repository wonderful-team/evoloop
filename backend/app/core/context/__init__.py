# Core Context Module
# Provides context injection utilities and thread-local state management
from .manager import ContextManager, EvoContext
from .plugins import plugin_registry
from .thread_store import thread_context_store
from .tool_state import tool_state_store

__all__ = [
    "ContextManager",
    "EvoContext",
    "plugin_registry",
    "thread_context_store",
    "tool_state_store",
]
