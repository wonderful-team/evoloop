import logging
from typing import Protocol, List, Optional
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


class WorkspaceProvider(Protocol):
    """
    Protocol for providing workspace-level context, such as project file structure.
    Normally implemented by the domain layer (e.g., app.domain.project).
    """
    async def get_project_structure(self, path: str) -> str:
        """Returns a string representation of the project structure at the given path."""
        ...


_workspace_provider: Optional[WorkspaceProvider] = None


def set_workspace_provider(provider: WorkspaceProvider):
    """Register the global WorkspaceProvider."""
    global _workspace_provider
    _workspace_provider = provider


def get_workspace_provider() -> Optional[WorkspaceProvider]:
    """Retrieve the global WorkspaceProvider."""
    return _workspace_provider
