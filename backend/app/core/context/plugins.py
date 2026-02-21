import logging
from typing import Protocol, List
from app.core.context.manager import EvoContext

logger = logging.getLogger(__name__)


class ContextPlugin(Protocol):
    """
    Protocol for context plugins.
    Domain modules should implement this to inject their specific
    state/knowledge into the generic EvoContext.
    """

    def hydrate(self, ctx: EvoContext) -> None:
        """Inject domain-specific knowledge into the context"""
        ...


class ContextPluginRegistry:
    """Registry for all context plugins."""

    def __init__(self):
        self._plugins: List[ContextPlugin] = []

    def register(self, plugin: ContextPlugin) -> None:
        self._plugins.append(plugin)
        logger.debug(f"Registered ContextPlugin: {plugin.__class__.__name__}")

    def hydrate_context(self, ctx: EvoContext) -> None:
        """
        Run all registered plugins to populate the given context.
        This provides a dependency-inversed way to load domain knowledge.
        """
        for plugin in self._plugins:
            try:
                plugin.hydrate(ctx)
            except Exception as e:
                logger.error(f"Error executing ContextPlugin {plugin.__class__.__name__}: {e}")


# Global registry instance
plugin_registry = ContextPluginRegistry()
