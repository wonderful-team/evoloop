import functools
import logging
from collections.abc import Callable
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine.state import AgentState

logger = logging.getLogger(__name__)


class ContextInjector:
    """
    Middleware Component that resolves and injects context dependencies.
    Acts as a Service Locator / dependency Resolver for Agent Nodes.
    """

    @staticmethod
    async def resolve(state: AgentState, injectables: list[str]) -> dict[str, Any]:
        """
        Resolves requested context keys into a dictionary.
        This isolates the Node from the complexity of fetching data (DB calls, API calls, File IO).
        """
        context = {}
        project_id = state.get("project_id", 1)  # Default to 1 if missing

        for key in injectables:
            try:
                if key == "memory":
                    # Lazy Import to avoid circular deps
                    from app.domain.memory.service import MemoryService

                    # Fetch concepts from Long-Term Memory (Knowledge Graph / Vector DB)
                    # We assume we want ALL concepts for the project for now,
                    # or perhaps context-relevant ones if 'context.snippets' exists.
                    context["memory"] = await MemoryService.get_project_concepts(project_id)

                elif key == "files":
                    # Flatten retrieval context files if present
                    retrieval = state.get("context", {})
                    files = retrieval.get("files", []) if retrieval else []
                    context["files"] = files

                elif key == "start_context":
                    # Legacy or specific start context
                    context["start_context"] = state.get("context", "")

                elif key == "current_plan":
                    context["current_plan"] = state.get("current_plan")

                elif key == "user_preferences":
                    context["user_preferences"] = state.get("user_preferences")

                elif key == "project_id":
                    context["project_id"] = project_id

                else:
                    logger.warning(f"Unknown injection key requested: {key}")
                    context[key] = None

            except Exception as e:
                logger.error(f"Failed to inject context '{key}': {e}")
                context[key] = None

        return context


def context_aware(inject: list[str]):
    """
    Decorator for LangGraph Nodes.

    Usage:
        @context_aware(inject=["memory", "files"])
        async def my_node(state, config, context):
            ...
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(state: AgentState, config: RunnableConfig, **kwargs):
            # 1. Resolve Context
            context_data = await ContextInjector.resolve(state, inject)

            # 2. Inject into kwargs or passing as 'context' arg
            # We enforce the node function signature to accept 'context'.
            # If the original function doesn't expect 'context', we might need to be careful?
            # But we control the nodes. We will standardize them to accept `context`.

            return await func(state, config, context=context_data, **kwargs)

        return wrapper

    return decorator
