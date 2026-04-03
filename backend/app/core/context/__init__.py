# Core Context Module
# Provides context injection utilities and thread-local state management
from .manager import ContextManager, EvoContext, get_context
from .cache import (
    LayeredContextCache,
    StaticContextLayer,
    DynamicContextLayer,
    get_context_cache_stats,
)
from .plugins import ContextPlugin, ContextPluginRegistry, plugin_registry
from .thread_store import thread_context_store
from .tool_state import ToolState, tool_state_store

__all__ = [
    "ContextManager",
    "EvoContext",
    "get_context",
    # Cache
    "LayeredContextCache",
    "StaticContextLayer",
    "DynamicContextLayer",
    "get_context_cache_stats",
    # Plugins
    "ContextPluginRegistry",
    "ContextPlugin",
    "plugin_registry",
    # Thread store
    "thread_context_store",
    # Tool state management
    "ToolState",
    "tool_state_store",
]
