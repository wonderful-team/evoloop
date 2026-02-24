# Core Context Module
# Provides context injection utilities
from .manager import ContextManager, EvoContext, get_context
from .plugins import ContextPlugin, ContextPluginRegistry, plugin_registry
from .thread_store import thread_context_store
from . import memory_plugin

__all__ = [
    "ContextManager",
    "EvoContext",
    "get_context",
    "ContextPluginRegistry",
    "ContextPlugin",
    "plugin_registry",
    "thread_context_store"
]
